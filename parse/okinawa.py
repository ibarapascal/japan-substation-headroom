"""Okinawa Electric Power.

Loading (two pages: bulk system and local system):
- FY2024 onward, CSV split in two per year: *_1.csv holds transmission lines (label 送電線No,
  skipped), *_2.csv holds transformers in the common layout (voltages written as '132kV').
  Local transformers are distribution transformers named '<substation> 配変N号'.
- FY2019-2023, Excel: sheets 送電線 (skipped), 変電所 (transformers) and index sheets (skipped).
  The 変電所 sheet has a title row, a header row starting 日付 / 時 with the column numbers or
  names, and timestamps as date + hour columns. Voltages are not given; they are filled from the
  CSV files of later years by substation name where available.
Capacity: sys_yoso_{kikan,local}_tr.csv, common template.
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Dict, Iterator, List, Optional, Tuple

from . import generic
from .common import clean_label, parse_hour, parse_ts
from .tables import iter_tables, source_label
from .wide import Block, ColMeta, make_block, norm_no, parse_wide_rows, to_value

log = logging.getLogger(__name__)
OPERATOR = "okinawa"
Lookup = Dict[str, Tuple[str, str]]

_NO = re.compile(r"^(No\.?\s*)?\(?\d+\)?(\s*-\s*\d+)?$", re.IGNORECASE)


def prepare(paths: List[str]) -> Lookup:
    """substation name -> (v1, v2) from the CSV transformer files."""
    lookup: Lookup = {}
    for path in sorted(paths):
        if not path.lower().endswith(".csv"):
            continue
        for tid, rows in iter_tables(path):
            b = parse_wide_rows(rows, tid, header_only=True)
            if b is None:
                continue
            for c in b.cols:
                if c.name and (c.v1 or c.v2):
                    lookup.setdefault(c.name, (c.v1, c.v2))
    return lookup


def sort_key(rel: str):
    return rel


def _row_ts(row) -> Optional[dt.datetime]:
    if not row:
        return None
    if len(row) > 1 and isinstance(row[1], dt.datetime):
        return row[1].replace(microsecond=0)
    t0 = parse_ts(row[0])
    if t0 is None:
        return None
    h = parse_hour(row[1]) if len(row) > 1 else None
    if h is not None and (t0.hour, t0.minute) == (0, 0):
        return t0 + dt.timedelta(hours=h)
    return t0


def parse_xlsx_sheet(rows, source: str, lookup: Lookup) -> Optional[Block]:
    """Sheet '変電所': header rows until the first timestamp row; the row whose cells look like
    column numbers is the No row, the other non-title row is the name row."""
    it = iter(rows)
    header: List[list] = []
    first = None
    for row in it:
        row = list(row)
        if _row_ts(row) is not None:
            first = row
            break
        header.append(row)
        if len(header) > 20:
            return None
    if first is None:
        return None
    no_row, name_row = None, None
    for r in header:
        cells = [clean_label(c) for c in r[2:]]
        nonempty = [c for c in cells if c]
        if not nonempty:
            continue
        if all(_NO.match(c) for c in nonempty):
            no_row = r
        elif any(("変電所" in c or "配変" in c) for c in nonempty):
            name_row = r
    if name_row is None:
        return None
    width = max(len(name_row), len(first))
    idx, cols = [], []
    for j in range(2, width):
        name = clean_label(name_row[j]) if j < len(name_row) else ""
        no = norm_no(no_row[j]) if no_row is not None and j < len(no_row) else ""
        no = re.sub(r"^No\.?\s*", "", no, flags=re.IGNORECASE)
        if not name and not no:
            continue
        v1, v2 = lookup.get(name, ("", ""))
        idx.append(j)
        cols.append(ColMeta(no, name, v1, v2, no or name))
    ts_list, vals = [], []

    def add(row):
        t = _row_ts(row)
        if t is None:
            return
        ts_list.append(t)
        vals.append([to_value(row[j])[0] if j < len(row) else float("nan") for j in idx])

    add(first)
    for row in it:
        add(list(row))
    return make_block(source, cols, ts_list, vals, None)


def load_blocks(path: str, rel: str, ctx: Optional[Lookup] = None) -> Iterator[Block]:
    lookup = ctx or {}
    if path.lower().endswith(".csv"):
        for b in generic.load_blocks(path, rel):
            yield b
        return
    for tid, rows in iter_tables(path):
        sheet = clean_label(tid.split("#")[-1])
        if sheet != "変電所":
            continue
        label = source_label(rel, tid)
        b = parse_xlsx_sheet(rows, label, lookup)
        if b is None:
            log.warning("no transformer table recognised in %s", label)
            continue
        yield b


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR)
