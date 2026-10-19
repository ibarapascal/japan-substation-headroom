"""One-command build from raw downloads to the derived tables.

Usage:
  python -m pipeline build --raw RAW_DIR --out OUT_DIR [--operators kansai,tepco]
                           [--format auto|parquet|csv] [--work DIR] [--keep-work]
  python -m pipeline history --raw RAW_DIR --out OUT_DIR   # see pipeline/history.py
  python -m pipeline sites --eegs EEGS_DIR --out OUT_DIR   # see pipeline/sites.py
  python -m pipeline compare --built OUT_DIR --released data/   # see pipeline/compare.py

RAW_DIR is one retrieval directory written by `python -m fetch download` (it holds manifest.csv).
Files are processed one at a time; identical files (same sha256) are processed once.

Outputs (OUT_DIR):
  capacity/capacity_table.{csv,parquet}
  load_long/<operator>.{parquet|csv.gz}        hourly long table (not redistributed)
  stats/bank_year_stats.csv
  stats/substation_year_stats.csv
  stats/column_duplicates.csv
  headroom/headroom_reconstructed.csv
  headroom/join_report.csv
  headroom/unmatched_keys.csv
  logs/parse_report.csv, logs/files.csv, logs/build.log
"""
from __future__ import annotations

import argparse
import csv
import logging
import os
import sys
import time
from typing import Dict, List, Optional

import numpy as np

from derive.headroom import HEADROOM_FIELDS, JOIN_REPORT_FIELDS, reconstruct
from parse.capacity import merge_split_rows
from derive.stats import BANK_FIELDS, DUP_FIELDS, STATION_FIELDS, Spill, aggregate_group
from parse import OPERATOR_IDS, operator_module
from parse.capacity import CAPACITY_FIELDS
from parse.names import substation_key
from pipeline.longtable import LongWriter

log = logging.getLogger("pipeline")

PARSE_REPORT_FIELDS = ["operator", "source_file", "n_columns", "n_hours", "first_ts_local",
                       "last_ts_local", "time_convention", "missing_share", "marked_values",
                       "notes"]
FILE_FIELDS = ["operator", "kind", "local_name", "sha256", "status", "tables", "seconds"]


def write_csv(path: str, fields: List[str], rows: List[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in fields})


def write_parquet(path: str, fields: List[str], rows: List[dict]) -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except Exception:
        return
    cols = {k: [r.get(k) for r in rows] for k in fields}
    pq.write_table(pa.table(cols), path, compression="zstd")


def list_files(raw: str, operators: List[str]) -> List[Dict[str, str]]:
    """Files to process from manifest.csv (falls back to a directory scan)."""
    mpath = os.path.join(raw, "manifest.csv")
    files: List[Dict[str, str]] = []
    if os.path.exists(mpath):
        with open(mpath, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r["operator"] in operators and r["kind"] in ("load_tr", "capacity_tr") \
                        and r["local_name"] and os.path.exists(os.path.join(raw, r["local_name"])):
                    files.append({"operator": r["operator"], "kind": r["kind"],
                                  "local_name": r["local_name"], "sha256": r["sha256"]})
    else:
        for op in operators:
            for kind in ("load_tr", "capacity_tr"):
                d = os.path.join(raw, op, kind)
                if os.path.isdir(d):
                    for fn in sorted(os.listdir(d)):
                        files.append({"operator": op, "kind": kind,
                                      "local_name": f"{op}/{kind}/{fn}", "sha256": ""})
        hist = os.path.join(raw, "tepco_history")
        if "tepco" in operators and os.path.isdir(hist):
            for root, _d, fns in os.walk(hist):
                for fn in sorted(fns):
                    if fn.endswith(".zip"):
                        files.append({"operator": "tepco", "kind": "load_tr", "sha256": "",
                                      "local_name": os.path.relpath(os.path.join(root, fn), raw)})
    return files


def column_key(name: str, sub_no: str, bank: str) -> str:
    """Join key of a loading column; '#<bank>' when the column has no usable name."""
    if not name or name == sub_no:
        return "#" + (bank or sub_no)
    k = substation_key(name)
    return k if k else "#" + (bank or sub_no)


def build(raw: str, out: str, operators: List[str], fmt: str, work: Optional[str],
          keep_work: bool) -> int:
    t0 = time.time()
    files = list_files(raw, operators)
    log.info("%d files listed", len(files))
    seen_sha: Dict[str, str] = {}
    file_rows: List[dict] = []
    # ---- capacity ----
    cap_rows: List[dict] = []
    for fr in [f for f in files if f["kind"] == "capacity_tr"]:
        mod = operator_module(fr["operator"])
        st = time.time()
        recs = mod.capacity_rows(os.path.join(raw, fr["local_name"]), fr["local_name"])
        cap_rows.extend(recs)
        file_rows.append({**fr, "status": "parsed", "tables": len(recs),
                          "seconds": round(time.time() - st, 2)})
    cap_rows, n_merged = merge_split_rows(cap_rows)
    log.info("capacity: merged %d records printed on several lines", n_merged)
    write_csv(os.path.join(out, "capacity", "capacity_table.csv"), CAPACITY_FIELDS, cap_rows)
    write_parquet(os.path.join(out, "capacity", "capacity_table.parquet"), CAPACITY_FIELDS, cap_rows)
    log.info("capacity rows: %d", len(cap_rows))
    # ---- loading ----
    spill = Spill(work or os.path.join(out, "_work"))
    parse_report: List[dict] = []
    for op in operators:
        mod = operator_module(op)
        op_files = [f for f in files if f["kind"] == "load_tr" and f["operator"] == op]
        if not op_files:
            continue
        op_files.sort(key=lambda f: mod.sort_key(f["local_name"]))
        ctx = mod.prepare([os.path.join(raw, f["local_name"]) for f in op_files])
        writer = LongWriter(os.path.join(out, "load_long", op), fmt)
        for fr in op_files:
            st = time.time()
            if fr["sha256"] and fr["sha256"] in seen_sha:
                file_rows.append({**fr, "status": f"duplicate_of:{seen_sha[fr['sha256']]}",
                                  "tables": 0, "seconds": 0})
                continue
            if fr["sha256"]:
                seen_sha[fr["sha256"]] = fr["local_name"]
            n_tables = 0
            try:
                for b in mod.load_blocks(os.path.join(raw, fr["local_name"]), fr["local_name"], ctx):
                    n_tables += 1
                    raw_names = [c.name for c in b.cols]
                    banks = [c.bank for c in b.cols]
                    keys = [column_key(c.name, c.sub_no, c.bank) for c in b.cols]
                    v1 = [c.v1 for c in b.cols]
                    v2 = [c.v2 for c in b.cols]
                    writer.write(op, b.source_file, raw_names, keys, banks, v1, v2, b.ts,
                                 b.values, b.marked)
                    spill.add(op, b.source_file, raw_names, keys, v1, v2, banks, b.ts, b.values)
                    nval = b.values.size
                    parse_report.append({
                        "operator": op, "source_file": b.source_file, "n_columns": len(b.cols),
                        "n_hours": len(b.ts),
                        "first_ts_local": str(b.ts[0]).replace("T", " ") if len(b.ts) else "",
                        "last_ts_local": str(b.ts[-1]).replace("T", " ") if len(b.ts) else "",
                        "time_convention": b.time_convention,
                        "missing_share": round(float(np.isnan(b.values).sum()) / nval, 4) if nval else None,
                        "marked_values": int(b.marked.sum()) if b.marked is not None else 0,
                        "notes": "; ".join(b.notes)})
                    del b
                status = "parsed" if n_tables else "no_table"
            except Exception as e:  # keep going; the failure is reported
                log.exception("failed: %s", fr["local_name"])
                status = f"error:{type(e).__name__}:{e}"
            file_rows.append({**fr, "status": status, "tables": n_tables,
                              "seconds": round(time.time() - st, 2)})
            log.info("%s %s tables=%d %.1fs", status, fr["local_name"], n_tables, time.time() - st)
        writer.close()
        log.info("%s long table rows: %d -> %s", op, writer.rows, os.path.basename(writer.path))
    write_csv(os.path.join(out, "logs", "parse_report.csv"), PARSE_REPORT_FIELDS, parse_report)
    write_csv(os.path.join(out, "logs", "files.csv"), FILE_FIELDS, file_rows)
    # ---- statistics ----
    bank_rows: List[dict] = []
    station_rows: List[dict] = []
    dup_rows: List[dict] = []
    for op, fy, stems in spill.groups():
        st = time.time()
        b, s, d = aggregate_group(op, fy, stems)
        bank_rows += b
        station_rows += s
        dup_rows += d
        log.info("stats %s FY%d: banks=%d stations=%d %.1fs", op, fy, len(b), len(s), time.time() - st)
    write_csv(os.path.join(out, "stats", "bank_year_stats.csv"), BANK_FIELDS, bank_rows)
    write_csv(os.path.join(out, "stats", "substation_year_stats.csv"), STATION_FIELDS, station_rows)
    write_csv(os.path.join(out, "stats", "column_duplicates.csv"), DUP_FIELDS, dup_rows)
    write_parquet(os.path.join(out, "stats", "substation_year_stats.parquet"), STATION_FIELDS, station_rows)
    # ---- headroom ----
    no_cap = {op for op in operators if not any(r["operator"] == op for r in cap_rows)}
    head, report = reconstruct(station_rows, cap_rows, no_cap)
    write_csv(os.path.join(out, "headroom", "headroom_reconstructed.csv"), HEADROOM_FIELDS, head)
    write_parquet(os.path.join(out, "headroom", "headroom_reconstructed.parquet"), HEADROOM_FIELDS, head)
    write_csv(os.path.join(out, "headroom", "join_report.csv"), JOIN_REPORT_FIELDS, report)
    latest = {r["operator"]: r["fiscal_year"] for r in report if r["is_latest_year"]}
    unmatched = [r for r in head if r["join_status"] in ("unmatched_key", "unmatched_voltage")
                 and latest.get(r["operator"]) == r["fiscal_year"]]
    write_csv(os.path.join(out, "headroom", "unmatched_keys.csv"),
              ["operator", "fiscal_year", "substation_key", "substation_raw", "v1_kv", "v2_kv",
               "join_status"], unmatched)
    if not keep_work:
        spill.cleanup()
    log.info("build finished in %.1f min", (time.time() - t0) / 60)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--raw", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--operators", default=",".join(OPERATOR_IDS))
    b.add_argument("--format", default="auto", choices=["auto", "parquet", "csv"])
    b.add_argument("--work", default=None, help="scratch directory (default OUT/_work)")
    b.add_argument("--keep-work", action="store_true")
    h = sub.add_parser("history", help="TEPCO capacity history from archived capacity lists")
    h.add_argument("--raw", required=True)
    h.add_argument("--out", required=True)
    s = sub.add_parser("sites", help="data center site register")
    s.add_argument("--eegs", required=True, help="directory holding national_office_<FY>.zip")
    s.add_argument("--out", required=True)
    c = sub.add_parser("compare", help="compare a rebuild with the released tables")
    c.add_argument("--built", required=True, help="output directory of a rebuild")
    c.add_argument("--released", default="data", help="released tables (default: data)")
    c.add_argument("--strict", action="store_true",
                   help="count released tables missing from the rebuild as differences")
    c.add_argument("--max-show", type=int, default=5, help="example differences per table")
    a = ap.parse_args(argv)
    if a.cmd == "compare":
        from pipeline.compare import compare_dirs
        return compare_dirs(a.built, a.released, a.strict, a.max_show)
    os.makedirs(os.path.join(a.out, "logs"), exist_ok=True)
    log_name = {"build": "build.log"}.get(a.cmd, f"{a.cmd}.log")
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout),
                  logging.FileHandler(os.path.join(a.out, "logs", log_name), encoding="utf-8")])
    if a.cmd == "history":
        from pipeline.history import build_history
        return build_history(a.raw, a.out)
    if a.cmd == "sites":
        from pipeline.sites import build_sites
        return build_sites(a.eegs, a.out)
    ops = [o.strip() for o in a.operators.split(",") if o.strip()]
    return build(a.raw, a.out, ops, a.format, a.work, a.keep_work)


if __name__ == "__main__":
    sys.exit(main())
