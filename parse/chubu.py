"""Chubu Electric Power Grid.

Loading: one Excel workbook per fiscal year (FY2018-2022: all levels in one workbook; FY2023
onward: one bulk-system workbook and one local-system workbook). File names are opaque
(rule_NN.xlsx / .xlsm) and are resolved from the link text on the operator page. Sheets: 275kV以上
(変圧器), 154kV(変圧器/バンク), 77kV以下バンク.
- FY2023 onward: common wide layout (labels 変電所No / 一次電圧 / 二次電圧 / 変電所名 in the first
  column, timestamps as Excel datetimes, two blank rows on top).
- FY2018-2022: only the 変電所No row is published (label '変電所No.→' in the fourth column); each
  hour is given as date / start time / '～' / end time in the first four columns. Names and
  voltages of these columns are filled from the newer workbooks by (sheet level, No); columns
  whose No does not appear in any newer workbook keep an empty name and an unjoinable key.
Capacity: no file is published (interactive map only); recorded in the manifest as
not_published_as_file.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, Iterator, List, Optional, Tuple

from .common import clean_label
from .tables import iter_tables, source_label
from .wide import Block, parse_wide_rows

log = logging.getLogger(__name__)
OPERATOR = "chubu"

Lookup = Dict[Tuple[str, str], Tuple[str, str, str]]


def sheet_level(table_id: str) -> str:
    sheet = clean_label(table_id.split("#")[-1])
    m = re.match(r"^(\d+)kV", sheet)
    return m.group(1) if m else sheet


def prepare(paths: List[str]) -> Lookup:
    """(sheet level, No) -> (name, v1, v2) from every table that publishes names."""
    lookup: Lookup = {}
    for path in sorted(paths):
        for tid, rows in iter_tables(path):
            b = parse_wide_rows(rows, tid, header_only=True)
            if b is None:
                continue
            lvl = sheet_level(tid)
            for c in b.cols:
                if c.sub_no and c.name:
                    lookup.setdefault((lvl, c.sub_no), (c.name, c.v1, c.v2))
    return lookup


def sort_key(rel: str):
    return rel


def load_blocks(path: str, rel: str, ctx: Optional[Lookup] = None) -> Iterator[Block]:
    lookup = ctx or {}
    for tid, rows in iter_tables(path):
        label = source_label(rel, tid)
        b = parse_wide_rows(rows, label)
        if b is None:
            log.warning("no transformer table recognised in %s", label)
            continue
        lvl = sheet_level(tid)
        filled = 0
        for c in b.cols:
            if not c.name and (lvl, c.sub_no) in lookup:
                c.name, v1, v2 = lookup[(lvl, c.sub_no)]
                c.v1 = c.v1 or v1
                c.v2 = c.v2 or v2
                filled += 1
        if filled:
            b.notes.append(f"names and voltages of {filled} columns taken from other fiscal years")
        yield b


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return []
