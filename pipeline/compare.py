"""Compare a rebuild with the released tables.

Usage:
  python -m pipeline compare --built BUILD_DIR --released data/ [--strict] [--max-show 5]

Every CSV under RELEASED is matched by relative path with a CSV under BUILT (e.g.
stats/substation_year_stats.csv). Rows are aligned on the key columns of each table (KEYS);
rows sharing a key are paired in sorted order. Cells are equal when the text is identical or when
both parse as numbers within an absolute tolerance of 1e-6 or a relative tolerance of 1e-9.

Reported per table: rows only in the release (missing), rows only in the rebuild (extra), and
the number of paired rows and cells that differ, with the first few differences.
Tables present on one side only are listed; a released table missing from the rebuild counts as a
difference only with --strict (a partial rebuild, e.g. without `pipeline history`, is allowed).
Input indexes (manifest*.csv) are not compared.

Exit status: 0 when all compared tables agree, 1 otherwise.
"""
from __future__ import annotations

import csv
import math
import os
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

ABS_TOL = 1e-6
REL_TOL = 1e-9

# relative path -> key columns. Tables not listed are compared on all columns (row multiset).
KEYS: Dict[str, Sequence[str]] = {
    "capacity/capacity_table.csv": ("operator", "source_file", "substation_raw", "v1_kv", "v2_kv"),
    "stats/substation_year_stats.csv": ("operator", "fiscal_year", "substation_key", "v1_kv", "v2_kv"),
    "stats/bank_year_stats.csv": ("operator", "fiscal_year", "source_file", "substation_raw",
                                  "bank", "v1_kv", "v2_kv"),
    "headroom/headroom_reconstructed.csv": ("operator", "fiscal_year", "substation_key", "v1_kv",
                                            "v2_kv"),
    "headroom/join_report.csv": ("operator", "fiscal_year"),
    "headroom/unmatched_keys.csv": ("operator", "fiscal_year", "substation_key", "v1_kv", "v2_kv"),
    "history/tepco_capacity_history.csv": ("source_file", "table_type", "voltage_class", "row_no"),
    "history/tepco_capacity_history_files.csv": ("file_name",),
    "history/distribution_area_summary.csv": ("area", "snapshot_date"),
    "sites/data_center_sites.csv": ("site_id",),
}


def _num(s: str) -> Optional[float]:
    try:
        v = float(s)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def cells_equal(a: str, b: str) -> bool:
    if a == b:
        return True
    x, y = _num(a), _num(b)
    if x is None or y is None:
        return False
    return abs(x - y) <= max(ABS_TOL, REL_TOL * max(abs(x), abs(y)))


def _sort_token(s: str) -> Tuple[int, float, str]:
    v = _num(s)
    return (0, v, "") if v is not None else (1, 0.0, s)


def read_table(path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        rows = [{k: (v or "") for k, v in row.items()} for row in r]
        return list(r.fieldnames or []), rows


def csv_files(root: str) -> List[str]:
    out = []
    for d, _dirs, files in os.walk(root, followlinks=True):
        for fn in files:
            if fn.endswith(".csv") and not fn.startswith("manifest"):
                out.append(os.path.relpath(os.path.join(d, fn), root).replace(os.sep, "/"))
    return sorted(out)


def _index(rows: Iterable[Dict[str, str]], key: Sequence[str], rest: Sequence[str]):
    groups: Dict[tuple, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        groups[tuple(r.get(k, "") for k in key)].append(r)
    for g in groups.values():
        g.sort(key=lambda r: [_sort_token(r.get(c, "")) for c in rest])
    return groups


def compare_table(built: str, released: str, key: Optional[Sequence[str]] = None,
                  max_show: int = 5) -> Dict[str, object]:
    """Compare two CSV files; returns counts and up to max_show example differences."""
    fb, rb = read_table(built)
    fr, rr = read_table(released)
    res: Dict[str, object] = {
        "rows_released": len(rr), "rows_built": len(rb),
        "columns_missing": [c for c in fr if c not in fb],
        "columns_extra": [c for c in fb if c not in fr],
        "missing_rows": 0, "extra_rows": 0, "rows_differing": 0, "cells_differing": 0,
        "examples": [],
    }
    cols = [c for c in fr if c in fb]
    key = [c for c in (key or cols) if c in cols]
    rest = [c for c in cols if c not in key]
    gb, gr = _index(rb, key, rest), _index(rr, key, rest)
    examples: List[str] = []
    for k in sorted(set(gb) | set(gr)):
        a, b = gr.get(k, []), gb.get(k, [])
        n = min(len(a), len(b))
        if len(a) > n:
            res["missing_rows"] += len(a) - n
            if len(examples) < max_show:
                examples.append(f"missing row {dict(zip(key, k))}")
        if len(b) > n:
            res["extra_rows"] += len(b) - n
            if len(examples) < max_show:
                examples.append(f"extra row {dict(zip(key, k))}")
        for ra, rb_ in zip(a[:n], b[:n]):
            bad = [c for c in rest if not cells_equal(ra.get(c, ""), rb_.get(c, ""))]
            if bad:
                res["rows_differing"] += 1
                res["cells_differing"] += len(bad)
                if len(examples) < max_show:
                    c = bad[0]
                    examples.append(f"{dict(zip(key, k))} {c}: released={ra.get(c, '')!r} "
                                    f"built={rb_.get(c, '')!r} ({len(bad)} cell(s))")
    res["examples"] = examples
    return res


def is_clean(res: Dict[str, object]) -> bool:
    return not (res["columns_missing"] or res["columns_extra"] or res["missing_rows"]
                or res["extra_rows"] or res["cells_differing"])


def compare_dirs(built: str, released: str, strict: bool = False, max_show: int = 5,
                 echo=print) -> int:
    rel, bui = csv_files(released), set(csv_files(built))
    ok = True
    compared = 0
    for path in rel:
        if path not in bui:
            echo(f"[not in built] {path}")
            ok = ok and not strict
            continue
        res = compare_table(os.path.join(built, path), os.path.join(released, path),
                            KEYS.get(path), max_show)
        compared += 1
        clean = is_clean(res)
        ok = ok and clean
        echo(f"[{'ok' if clean else 'DIFF'}] {path}: released={res['rows_released']} "
             f"built={res['rows_built']} missing={res['missing_rows']} extra={res['extra_rows']} "
             f"rows_differing={res['rows_differing']} cells_differing={res['cells_differing']}")
        if res["columns_missing"] or res["columns_extra"]:
            echo(f"    columns missing={res['columns_missing']} extra={res['columns_extra']}")
        for e in res["examples"]:
            echo(f"    {e}")
    for path in sorted(bui - set(rel)):
        echo(f"[not released] {path}")
    echo(f"compared {compared} table(s): {'all equal' if ok else 'differences found'}")
    return 0 if ok else 1
