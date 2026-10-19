"""Generic parser for the common "wide" hourly loading layout.

Layout (most operators): a few header rows whose first cell is a label, followed by one row per
hour whose first cell is a timestamp and whose remaining cells are one value per transformer
column.

  label rows   : 変電所No / 変電所番号 / 略号 / 設備No -> column identifier (published "No")
                 変電所名 / 設備名 / 名称              -> substation name
                 一次電圧 / 電圧(一次)     -> primary voltage [kV]
                 二次電圧 / 電圧(二次)     -> secondary voltage [kV]
  other rows before the first timestamp (units, notes, footnote markers) are ignored.

Labels are matched by prefix after NFKC normalisation and removal of quotes/apostrophes, so
"変電所No.", "'変電所No.", "変電所 No" and "変電所No.→" all match. The label may sit in a column
other than the first (one operator places it in the fourth column and spreads the timestamp over
the first columns as date / start time / "～" / end time).

Timestamps: if the first data row is at hh=01:00 the file uses hour-ending labels (01:00 ... 24:00
or next-day 00:00); all timestamps of such a block are shifted back one hour so ts is always the
start of the hourly interval.
"""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np

from .common import clean_label, norm_kv, parse_date, parse_hour, parse_ts

LABEL_PATTERNS: Dict[str, re.Pattern] = {
    "sub_no": re.compile(r"^(変電所\s*No|変電所番号|略号|設備\s*No|No\.?$)", re.IGNORECASE),
    "name": re.compile(r"^(変電所名|設備名|名称$|変電所$)"),
    "v1": re.compile(r"^(一次\s*電圧|電圧\s*\(?一次\)?|1次\s*電圧)"),
    "v2": re.compile(r"^(二次\s*電圧|電圧\s*\(?二次\)?|2次\s*電圧)"),
    "kv": re.compile(r"^電圧\s*[\[(]"),
    "send": re.compile(r"^送電端"),
    "recv": re.compile(r"^受電端"),
}


_NAME_KV = re.compile(r"[(（]\s*(\d+(?:\.\d+)?)\s*kV\s*[)）]", re.IGNORECASE)


@dataclass
class ColMeta:
    sub_no: str
    name: str
    v1: str
    v2: str
    bank: str


@dataclass
class Block:
    """One parsed table: hourly values for a set of transformer columns."""
    source_file: str
    cols: List[ColMeta]
    ts: np.ndarray                       # datetime64[s], interval start, local time
    values: np.ndarray                   # float64 (n_ts, n_cols), NaN = missing
    marked: Optional[np.ndarray] = None  # bool (n_ts, n_cols): value carried an asterisk mark
    time_convention: str = "hour_beginning"
    notes: List[str] = field(default_factory=list)


def to_value(v) -> Tuple[float, bool]:
    """Cell -> (value or NaN, asterisk-marked)."""
    if v is None:
        return np.nan, False
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v), False
    s = v if isinstance(v, str) else str(v)
    try:
        return float(s), False
    except ValueError:
        pass
    t = clean_label(s)
    marked = False
    if t.startswith("*") and len(t) > 1:
        marked, t = True, t[1:].strip()
    t = t.replace(",", "").replace("−", "-").replace("–", "-")
    try:
        return float(t), marked
    except ValueError:
        return np.nan, False


def _find_labels(header_rows: List[Sequence], max_label_col: int = 6) -> Tuple[Dict[str, Sequence], int]:
    roles: Dict[str, Sequence] = {}
    label_col = -1
    for row in header_rows:
        for j in range(min(max_label_col, len(row))):
            lab = clean_label(row[j])
            if not lab:
                continue
            for role, pat in LABEL_PATTERNS.items():
                if role not in roles and pat.search(lab):
                    roles[role] = row
                    if label_col < 0:
                        label_col = j
                    break
            break  # only the first non-empty cell of a row can be its label
    return roles, label_col


def _row_ts(row: Sequence, label_col: int) -> Optional[dt.datetime]:
    """Timestamp of a data row, read from the cells left of (and including) the label column.
    Leading empty cells are skipped; a date followed by an hour cell (start time) is combined."""
    if not row:
        return None
    cells = list(row[:max(label_col, 0) + 1])
    k = 0
    while k < len(cells) and (cells[k] is None or clean_label(cells[k]) == ""):
        k += 1
    if k >= len(cells):
        return None
    first = cells[k]
    if k + 1 < len(row) and k + 1 <= max(label_col, 0):
        h = parse_hour(row[k + 1])
        d = parse_date(first)
        if d is None:
            t0 = parse_ts(first)
            d = t0.date() if t0 is not None and (t0.hour, t0.minute) == (0, 0) else None
        if d is not None and h is not None:
            return dt.datetime(d.year, d.month, d.day) + dt.timedelta(hours=h)
    return parse_ts(first)


def _cell(row: Sequence, j: int):
    return row[j] if j < len(row) else None


def norm_no(v) -> str:
    """Published column number; '12.0' (spreadsheet float) -> '12'."""
    s = clean_label(v)
    return s[:-2] if re.fullmatch(r"\d+\.0", s) else s


def default_col_builder(j: int, roles: Dict[str, Sequence]) -> Optional[ColMeta]:
    """Column j -> ColMeta from the label rows; None for columns without No and name.
    A column with voltages but blank No and name is the continuation of a merged cell: it takes
    the No and name of the nearest named column to its left (at most 3 columns away)."""
    sub_no = norm_no(_cell(roles.get("sub_no", []), j))
    name = clean_label(_cell(roles.get("name", []), j))
    v1 = norm_kv(_cell(roles.get("v1", []), j))
    v2 = norm_kv(_cell(roles.get("v2", []), j))
    if not sub_no and not name and (v1 or v2):
        for k in range(j - 1, max(j - 4, 0), -1):
            sub_no = norm_no(_cell(roles.get("sub_no", []), k))
            name = clean_label(_cell(roles.get("name", []), k))
            if sub_no or name:
                break
    if not sub_no and not name:
        return None
    if not v1 and not v2:
        m = _NAME_KV.search(name)
        if m:  # e.g. "中能登変電所(500kV)": voltage of the transformer group given in the name
            v1 = norm_kv(m.group(1))
    return ColMeta(sub_no, name, v1, v2, sub_no or name)


def parse_wide_rows(rows: Iterable[Sequence], source_file: str,
                    col_builder: Optional[Callable[[int, Dict[str, Sequence]], Optional[ColMeta]]] = None,
                    max_header_rows: int = 80, header_only: bool = False) -> Optional[Block]:
    """Parse one table. Returns None if no label rows / no timestamp rows are found.
    col_builder(j, roles) may be given to select columns and build their metadata.
    header_only=True stops after the column metadata (values are left empty)."""
    it = iter(rows)
    header: List[Sequence] = []
    first_data: Optional[Sequence] = None
    for row in it:
        row = list(row) if row is not None else []
        if header:
            roles, lc = _find_labels(header)
            if roles and lc >= 0 and _row_ts(row, lc) is not None:
                first_data = row
                break
        header.append(row)
        if len(header) > max_header_rows:
            return None
    if first_data is None:
        return None
    roles, label_col = _find_labels(header)
    width = max(len(r) for r in list(roles.values()) + [first_data])
    build = col_builder or default_col_builder
    idx = []
    cols: List[ColMeta] = []
    for j in range(label_col + 1, width):
        meta = build(j, roles)
        if meta is None:
            continue
        idx.append(j)
        cols.append(meta)
    if not cols:
        return None
    if header_only:
        return Block(source_file, cols, np.array([], dtype="datetime64[s]"),
                     np.zeros((0, len(cols))))
    ts_list: List[dt.datetime] = []
    vals: List[List[float]] = []
    marks: List[List[bool]] = []
    any_mark = False

    def add(row: Sequence) -> None:
        nonlocal any_mark
        t = _row_ts(row, label_col)
        if t is None:
            return
        ts_list.append(t)
        rv, rm = [], []
        n = len(row)
        for j in idx:
            v, m = to_value(row[j]) if j < n else (np.nan, False)
            rv.append(v)
            rm.append(m)
            any_mark = any_mark or m
        vals.append(rv)
        marks.append(rm)

    add(first_data)
    for row in it:
        if row is None:
            continue
        add(list(row))
    return make_block(source_file, cols, ts_list, vals, marks if any_mark else None)


def make_block(source_file: str, cols: List[ColMeta], ts_list: List[dt.datetime],
               vals: List[List[float]], marks: Optional[List[List[bool]]]) -> Block:
    convention = "hour_beginning"
    if ts_list and ts_list[0].hour == 1 and ts_list[0].minute == 0:
        convention = "hour_ending"
        ts_list = [t - dt.timedelta(hours=1) for t in ts_list]
    ts = np.array(ts_list, dtype="datetime64[s]")
    values = np.array(vals, dtype=np.float64).reshape(len(ts_list), len(cols))
    marked = np.array(marks, dtype=bool).reshape(values.shape) if marks is not None else None
    return Block(source_file, cols, ts, values, marked, convention)
