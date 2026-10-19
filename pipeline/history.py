"""Build the TEPCO capacity history panel from archived capacity-list PDFs.

Usage:
  python -m pipeline history --raw RAW_DIR --out OUT_DIR

RAW_DIR is searched recursively for files named akiyouryou_<area>_<YYYYMMDDhhmmss>.pdf (the
Internet Archive capture timestamp is part of the name; see fetch/tepco_history.py). Files are
read one at a time through pdftotext; the PDFs themselves are not written to OUT_DIR.

Outputs (OUT_DIR/history/):
  tepco_capacity_history.csv         long table, one row per snapshot x published table row
  tepco_capacity_history_files.csv   file index: name, capture time, URLs, bytes, sha256, status
  distribution_area_summary.csv      per area x snapshot: rows, zero-available rows, median
"""
from __future__ import annotations

import csv
import logging
import os
import statistics
import time
from typing import Dict, List

from fetch.http import sha256_file
from fetch.tepco_history import original_url, wayback_url
from parse.tepco_history import HISTORY_FIELDS, iter_pdfs, parse_file_name, parse_pdf

log = logging.getLogger("pipeline.history")

FILE_FIELDS = ["file_name", "area", "capture_timestamp", "snapshot_date", "as_of",
               "original_url", "wayback_url", "bytes", "sha256", "status", "n_rows",
               "n_positional", "n_anchor", "n_skipped"]
SUMMARY_FIELDS = ["area", "snapshot_date", "as_of", "n_rows", "n_with_value", "n_zero",
                  "zero_share", "median_available_mw"]


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return v


def summarise(rows: List[Dict[str, object]]) -> List[Dict[str, object]]:
    """Distribution-area rows per area and snapshot: count, zero available capacity, median."""
    groups: Dict[tuple, List[Dict[str, object]]] = {}
    for r in rows:
        if r["table_type"] == "distribution_area":
            groups.setdefault((r["area"], r["snapshot_date"]), []).append(r)
    out = []
    for (area, date), g in sorted(groups.items()):
        vals = [r["available_mw_published"] for r in g if r["available_mw_published"] is not None]
        nz = sum(1 for v in vals if v == 0)
        out.append({"area": area, "snapshot_date": date, "as_of": g[0]["as_of"], "n_rows": len(g),
                    "n_with_value": len(vals), "n_zero": nz,
                    "zero_share": round(nz / len(vals), 4) if vals else "",
                    "median_available_mw": _fmt(statistics.median(vals)) if vals else ""})
    return out


def build_history(raw: str, out: str) -> int:
    t0 = time.time()
    odir = os.path.join(out, "history")
    os.makedirs(odir, exist_ok=True)
    files: List[Dict[str, object]] = []
    all_rows: List[Dict[str, object]] = []
    path_rows = os.path.join(odir, "tepco_capacity_history.csv")
    with open(path_rows, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HISTORY_FIELDS)
        w.writeheader()
        for path, fn in iter_pdfs(raw):
            area, ts, date = parse_file_name(fn)
            rows, st, readable = parse_pdf(path, fn)
            status = "parsed" if rows else ("no_rows" if readable else "unreadable")
            for r in rows:
                w.writerow({k: _fmt(r.get(k)) for k in HISTORY_FIELDS})
            # keep only the fields needed for the summary in memory
            all_rows.extend({"area": r["area"], "snapshot_date": r["snapshot_date"],
                             "as_of": r["as_of"], "table_type": r["table_type"],
                             "available_mw_published": r["available_mw_published"]}
                            for r in rows if r["table_type"] == "distribution_area")
            files.append({"file_name": fn, "area": area, "capture_timestamp": ts,
                          "snapshot_date": date, "as_of": rows[0]["as_of"] if rows else "",
                          "original_url": original_url(area), "wayback_url": wayback_url(fn),
                          "bytes": os.path.getsize(path), "sha256": sha256_file(path),
                          "status": status, "n_rows": st["rows"], "n_positional": st["positional"],
                          "n_anchor": st["anchor"], "n_skipped": st["skipped"]})
            log.info("%s %s rows=%d anchor=%d skipped=%d", status, fn, st["rows"], st["anchor"],
                     st["skipped"])
    with open(os.path.join(odir, "tepco_capacity_history_files.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FILE_FIELDS)
        w.writeheader()
        w.writerows(files)
    with open(os.path.join(odir, "distribution_area_summary.csv"), "w", newline="",
              encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=SUMMARY_FIELDS)
        w.writeheader()
        w.writerows(summarise(all_rows))
    n_ok = sum(1 for f in files if f["status"] == "parsed")
    log.info("history: %d files (%d parsed), %.1f s", len(files), n_ok, time.time() - t0)
    return 0
