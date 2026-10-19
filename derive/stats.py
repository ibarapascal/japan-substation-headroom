"""Bank-year and substation-year statistics from parsed hourly tables.

Parsed tables are first spilled to a work directory split by operator and fiscal year (April to
March, local time). Each (operator, fiscal year) is then aggregated on its own, so memory is
bounded by the largest operator-year (about n_columns x 8784 doubles).

Column identity within an operator-year is (substation_key, v1_kv, v2_kv, bank). When the same
identity is published by several files (overlapping regional files, repeated releases, files
split by half-year), hours are filled from the first file processed and later files only fill
hours still empty; differing overlapping values are counted as conflicts. Two identities that
share (substation_key, bank) but differ in voltage label and carry the same values (>=95% of at
least 24 overlapping non-zero hours equal within 0.5 MW) are treated as one column published in
two voltage-group files; the later one is dropped.

Substation-year series: banks of one substation and one secondary voltage (or, when the secondary
voltage is not published, one primary voltage group) are summed hour by hour. An hour enters the
series only if every bank that reports at least one value in that fiscal year has a value in that
hour (coincident sum over a complete set of banks).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import shutil
from collections import defaultdict
from typing import Dict, Iterator, List, Optional, Tuple

import numpy as np

from parse.common import fy_hours, fy_start, kv_value

Ident = Tuple[str, str, str, str]  # key, v1, v2, bank

BANK_FIELDS = ["operator", "fiscal_year", "substation_key", "substation_raw", "v1_kv", "v2_kv",
               "bank", "source_file", "hours_in_year", "valid_hours", "missing_hours",
               "zero_hours", "negative_hours", "max_mw", "max_ts_local", "min_mw", "mean_mw",
               "p99_mw", "p95_mw"]
STATION_FIELDS = ["operator", "fiscal_year", "substation_key", "substation_raw", "v2_kv",
                  "v1_kv", "n_banks", "n_banks_reporting", "hours_in_year", "valid_hours",
                  "peak_mw", "peak_ts_local", "p99_mw", "p95_mw", "zero_hours",
                  "negative_hours", "bank_zero_hours", "bank_negative_hours", "n_source_files"]
DUP_FIELDS = ["operator", "fiscal_year", "substation_key", "bank", "v1_kv", "v2_kv",
              "kind", "source_file", "other_source_file", "overlap_hours", "conflict_hours"]


class Spill:
    """Write parsed tables to <work>/<operator>/<fy>/<seq>.npz + .json."""

    def __init__(self, work_dir: str):
        self.work = work_dir
        self.seq = 0
        os.makedirs(work_dir, exist_ok=True)

    def add(self, operator: str, source_file: str, raw: List[str], keys: List[str],
            v1: List[str], v2: List[str], banks: List[str], ts: np.ndarray,
            values: np.ndarray) -> List[int]:
        if values.size == 0:
            return []
        t = ts.astype("datetime64[s]").astype("int64")
        years = ts.astype("datetime64[Y]").astype(int) + 1970
        months = ts.astype("datetime64[M]").astype(int) % 12 + 1
        fys = np.where(months >= 4, years, years - 1)
        out = []
        for fy in np.unique(fys):
            fy = int(fy)
            sel = fys == fy
            start = int(np.datetime64(fy_start(fy), "s").astype("int64"))
            hidx = ((t[sel] - start) // 3600).astype(np.int32)
            d = os.path.join(self.work, operator, str(fy))
            os.makedirs(d, exist_ok=True)
            self.seq += 1
            stem = os.path.join(d, f"{self.seq:07d}")
            np.savez(stem + ".npz", hidx=hidx, values=values[sel])
            with open(stem + ".json", "w", encoding="utf-8") as f:
                json.dump({"source_file": source_file, "raw": raw, "keys": keys, "v1": v1,
                           "v2": v2, "banks": banks}, f, ensure_ascii=False)
            out.append(fy)
        return out

    def groups(self) -> Iterator[Tuple[str, int, List[str]]]:
        for op in sorted(os.listdir(self.work)):
            od = os.path.join(self.work, op)
            if not os.path.isdir(od):
                continue
            for fy in sorted(os.listdir(od), key=int):
                fd = os.path.join(od, fy)
                stems = sorted(p[:-5] for p in os.listdir(fd) if p.endswith(".json"))
                yield op, int(fy), [os.path.join(fd, s) for s in stems]

    def cleanup(self) -> None:
        shutil.rmtree(self.work, ignore_errors=True)


def _pct(x: np.ndarray, q: float) -> Optional[float]:
    return float(np.percentile(x, q)) if x.size else None


def _ts_text(fy: int, h: int) -> str:
    return (fy_start(fy) + dt.timedelta(hours=int(h))).strftime("%Y-%m-%d %H:%M")


def _r(x: Optional[float], nd: int = 3) -> Optional[float]:
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def aggregate_group(operator: str, fy: int, stems: List[str]) -> Tuple[List[dict], List[dict], List[dict]]:
    """Return (bank rows, station rows, duplicate/conflict rows) for one operator-year."""
    n_hours = fy_hours(fy)
    metas = []
    ident_index: Dict[Ident, int] = {}
    ident_meta: List[dict] = []
    for s in stems:
        with open(s + ".json", encoding="utf-8") as f:
            m = json.load(f)
        metas.append(m)
        for j in range(len(m["keys"])):
            ident = (m["keys"][j], m["v1"][j], m["v2"][j], m["banks"][j])
            if ident not in ident_index:
                ident_index[ident] = len(ident_meta)
                ident_meta.append({"ident": ident, "raw": m["raw"][j],
                                   "source": m["source_file"], "sources": {m["source_file"]}})
            else:
                ident_meta[ident_index[ident]]["sources"].add(m["source_file"])
    M = np.full((len(ident_meta), n_hours), np.nan)
    dups: List[dict] = []
    for s, m in zip(stems, metas):
        z = np.load(s + ".npz")
        hidx, vals = z["hidx"], z["values"]
        ok = (hidx >= 0) & (hidx < n_hours)
        hidx, vals = hidx[ok], vals[ok]
        for j in range(vals.shape[1]):
            ident = (m["keys"][j], m["v1"][j], m["v2"][j], m["banks"][j])
            r = ident_index[ident]
            cur = M[r, hidx]
            new = vals[:, j]
            both = ~np.isnan(cur) & ~np.isnan(new)
            if both.any():
                conflict = int((np.abs(cur[both] - new[both]) > 1e-6).sum())
                dups.append({"operator": operator, "fiscal_year": fy, "substation_key": ident[0],
                             "bank": ident[3], "v1_kv": ident[1], "v2_kv": ident[2],
                             "kind": "repeated_column", "source_file": m["source_file"],
                             "other_source_file": ident_meta[r]["source"],
                             "overlap_hours": int(both.sum()), "conflict_hours": conflict})
            fill = np.isnan(cur) & ~np.isnan(new)
            if fill.any():
                cur[fill] = new[fill]
                M[r, hidx] = cur
    # same (key, bank) under different voltage labels with identical values -> drop later one
    drop = set()
    by_kb: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for i, im in enumerate(ident_meta):
        by_kb[(im["ident"][0], im["ident"][3])].append(i)
    for idxs in by_kb.values():
        if len(idxs) < 2:
            continue
        for a_pos, a in enumerate(idxs):
            if a in drop:
                continue
            for b in idxs[a_pos + 1:]:
                if b in drop:
                    continue
                both = ~np.isnan(M[a]) & ~np.isnan(M[b])
                nz = both & ((M[a] != 0) | (M[b] != 0))
                if nz.sum() < 24:
                    continue
                eq = np.abs(M[a][nz] - M[b][nz]) <= 0.5
                if eq.mean() >= 0.95:
                    drop.add(b)
                    ib = ident_meta[b]["ident"]
                    dups.append({"operator": operator, "fiscal_year": fy, "substation_key": ib[0],
                                 "bank": ib[3], "v1_kv": ib[1], "v2_kv": ib[2],
                                 "kind": "same_values_other_voltage_label",
                                 "source_file": ident_meta[b]["source"],
                                 "other_source_file": ident_meta[a]["source"],
                                 "overlap_hours": int(nz.sum()),
                                 "conflict_hours": int((~eq).sum())})
    bank_rows: List[dict] = []
    stations: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for i, im in enumerate(ident_meta):
        if i in drop:
            continue
        key, v1, v2, bank = im["ident"]
        x = M[i]
        valid = ~np.isnan(x)
        xv = x[valid]
        amax = int(np.nanargmax(x)) if xv.size else None
        bank_rows.append({
            "operator": operator, "fiscal_year": fy, "substation_key": key,
            "substation_raw": im["raw"], "v1_kv": v1, "v2_kv": v2, "bank": bank,
            "source_file": im["source"], "hours_in_year": n_hours,
            "valid_hours": int(valid.sum()), "missing_hours": int(n_hours - valid.sum()),
            "zero_hours": int((xv == 0).sum()), "negative_hours": int((xv < 0).sum()),
            "max_mw": _r(xv.max()) if xv.size else None,
            "max_ts_local": _ts_text(fy, amax) if amax is not None else "",
            "min_mw": _r(xv.min()) if xv.size else None,
            "mean_mw": _r(xv.mean()) if xv.size else None,
            "p99_mw": _r(_pct(xv, 99)), "p95_mw": _r(_pct(xv, 95)),
        })
        stations[(key, v2 if v2 else "v1:" + v1)].append(i)
    station_rows: List[dict] = []
    for (key, vgroup), idxs in stations.items():
        S = M[idxs]
        reporting = ~np.isnan(S).all(axis=1)
        R = S[reporting]
        v2 = "" if vgroup.startswith("v1:") else vgroup
        v1s = sorted({ident_meta[i]["ident"][1] for i in idxs} - {""},
                     key=lambda s: -(kv_value(s) or 0))
        raws = [ident_meta[i]["raw"] for i in idxs]
        raw = max(set(raws), key=raws.count)
        srcs = set().union(*(ident_meta[i]["sources"] for i in idxs))
        row = {"operator": operator, "fiscal_year": fy, "substation_key": key,
               "substation_raw": raw, "v2_kv": v2, "v1_kv": ";".join(v1s),
               "n_banks": len(idxs), "n_banks_reporting": int(reporting.sum()),
               "hours_in_year": n_hours, "valid_hours": 0, "peak_mw": None, "peak_ts_local": "",
               "p99_mw": None, "p95_mw": None, "zero_hours": 0, "negative_hours": 0,
               "bank_zero_hours": int(np.nansum(S == 0)),
               "bank_negative_hours": int(np.nansum(S < 0)),
               "n_source_files": len(srcs)}
        if R.shape[0]:
            valid = ~np.isnan(R).any(axis=0)
            tot = R[:, valid].sum(axis=0)
            if tot.size:
                h = np.flatnonzero(valid)[int(np.argmax(tot))]
                row.update({"valid_hours": int(valid.sum()), "peak_mw": _r(tot.max()),
                            "peak_ts_local": _ts_text(fy, h), "p99_mw": _r(_pct(tot, 99)),
                            "p95_mw": _r(_pct(tot, 95)), "zero_hours": int((tot == 0).sum()),
                            "negative_hours": int((tot < 0).sum())})
        station_rows.append(row)
    return bank_rows, station_rows, dups
