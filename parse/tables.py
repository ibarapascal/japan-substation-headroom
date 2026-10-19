"""Enumerate the tables inside a downloaded file: a CSV is one table, a workbook yields one table
per sheet, and a zip archive yields the tables of each member (members are read one at a time).

Each table is (table_id, rows): table_id is "" for a plain CSV, "#<sheet>" for a workbook sheet,
"<member>" or "<member>#<sheet>" for zip members; rows is an iterable of cell sequences.
"""
from __future__ import annotations

import os
from typing import Callable, Iterable, Iterator, Optional, Sequence, Tuple

from .common import csv_rows, iter_zip, xls_sheets, xlsx_sheets

Table = Tuple[str, Iterable[Sequence[object]]]


def _tables_from_bytes(name: str, raw: bytes,
                       member_filter: Optional[Callable[[str], bool]]) -> Iterator[Table]:
    low = name.lower()
    if low.endswith(".zip"):
        for member, data in iter_zip(raw):
            if member_filter is not None and not member_filter(member):
                continue
            for tid, rows in _tables_from_bytes(member, data, None):
                yield tid, rows
    elif low.endswith(".csv"):
        rows, _enc = csv_rows(raw)
        yield name, rows
    elif low.endswith((".xlsx", ".xlsm")):
        for sheet, rows in xlsx_sheets(raw):
            yield f"{name}#{sheet}", rows
    elif low.endswith(".xls"):
        for sheet, rows in xls_sheets(raw):
            yield f"{name}#{sheet}", rows


def iter_tables(path: str, member_filter: Optional[Callable[[str], bool]] = None) -> Iterator[Table]:
    """Yield tables of one file. member_filter(name) selects zip members (default: all)."""
    with open(path, "rb") as f:
        raw = f.read()
    base = os.path.basename(path)
    if base.lower().endswith(".zip"):
        for member, data in iter_zip(raw):
            if member_filter is not None and not member_filter(member):
                continue
            for tid, rows in _tables_from_bytes(member, data, None):
                yield tid, rows
    else:
        for tid, rows in _tables_from_bytes(base, raw, None):
            yield tid.replace(base, "", 1), rows


def source_label(rel: str, table_id: str) -> str:
    """'<rel path>' + '!<zip member>' and/or '#<sheet>'."""
    if not table_id:
        return rel
    return rel + (table_id if table_id.startswith("#") else "!" + table_id)
