"""TEPCO Power Grid.

Loading files (tyouryu_{kikan,154kV,66kV}.zip and archived predecessors) differ from the common
layout: a single header row "日時","<station>(変) - <element>",... and timestamps written as
"YYYY年MM月DD日 HH時" (older files: "... HH時MM分SS秒"). There are no voltage rows; the voltage
group is taken from the archive or member name (66kV group, 154kV group, bulk >=275kV group).

Columns kept: transformer elements only, i.e. the element part matches "<n>B", "<n>・<m>B"
(banks), "<n>号連絡Tr" (interconnecting transformers). Line columns ("...L", names containing 線)
are dropped. A multi-bank column such as "1・2・3B" is the published sum of banks 1, 2, 3; it is
kept only when none of its constituent banks is published individually for the same station in
the same file, so no bank is counted twice.

Capacity files (csv_yosochoryu_*.zip, member *_hendensyo.csv) have a six-row header with merged
cells; columns are read by position after checking the header. The first column encodes area,
publisher class and number, e.g. "変東京都(23区) 配電用変電所 323" or "変基幹 275kV 1-1". Voltage
is left blank by the publisher for distribution substations (22 kV and below).
"""
from __future__ import annotations

import datetime as dt
import logging
import re
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from .capacity import capacity_record, as_of_from
from .common import clean_label, norm_kv, parse_ts
from .tables import iter_tables, source_label
from .wide import Block, ColMeta, make_block, to_value

log = logging.getLogger(__name__)

OPERATOR = "tepco"
_ELEMENT = re.compile(r"^(?P<nums>\d+(?:[・,]\d+)*)\s*(?P<kind>B|号連絡Tr|号Tr|連絡Tr)$")


def voltage_group(name: str) -> str:
    """'66' / '154' / '' (bulk system, >=275 kV primary) from a file or member name."""
    n = clean_label(name)
    if "66kV" in n:
        return "66"
    if "154kV" in n:
        return "154"
    return ""


def group_priority(rel: str) -> int:
    """Process the lower voltage groups first so a column repeated in a higher-group file is
    recognised as a duplicate of the more specific one."""
    g = voltage_group(rel)
    return {"66": 0, "154": 1}.get(g, 2)


def split_column(header: str) -> Optional[Tuple[str, str, Tuple[str, ...], str]]:
    """'お茶の水(変) - 1・2B' -> ('お茶の水(変)', '1・2B', ('1','2'), 'B'); None if not a transformer."""
    h = clean_label(header)
    if " - " not in h:
        return None
    station, element = h.rsplit(" - ", 1)
    element = element.strip()
    if "線" in element:
        return None
    m = _ELEMENT.match(element)
    if not m:
        return None
    nums = tuple(re.split(r"[・,]", m.group("nums")))
    return station.strip(), element, nums, m.group("kind")


def select_columns(header: Sequence[str]) -> List[Tuple[int, str, str]]:
    """Return [(index, station, element)] of transformer columns, multi-bank sums removed when
    their constituents are published individually."""
    parsed = []
    singles: Dict[Tuple[str, str], set] = {}
    for j, h in enumerate(header):
        if j == 0:
            continue
        p = split_column(h)
        if p is None:
            continue
        station, element, nums, kind = p
        parsed.append((j, station, element, nums, kind))
        if len(nums) == 1:
            singles.setdefault((station, kind), set()).add(nums[0])
    keep = []
    seen = set()
    for j, station, element, nums, kind in parsed:
        if len(nums) > 1 and singles.get((station, kind), set()) & set(nums):
            continue
        if (station, element) in seen:
            continue
        seen.add((station, element))
        keep.append((j, station, element))
    return keep


def parse_load_table(rows, source: str, group: str) -> Optional[Block]:
    it = iter(rows)
    header = next(it, None)
    if not header or clean_label(header[0]) != "日時":
        return None
    sel = select_columns(header)
    if not sel:
        return None
    cols = [ColMeta("", station, group, "", element) for _j, station, element in sel]
    idx = [j for j, _s, _e in sel]
    ts_list: List[dt.datetime] = []
    vals, marks = [], []
    any_mark = False
    for row in it:
        if not row:
            continue
        t = parse_ts(row[0])
        if t is None:
            continue
        ts_list.append(t)
        rv, rm = [], []
        n = len(row)
        for j in idx:
            v, m = to_value(row[j]) if j < n else (float("nan"), False)
            rv.append(v)
            rm.append(m)
            any_mark = any_mark or m
        vals.append(rv)
        marks.append(rm)
    return make_block(source, cols, ts_list, vals, marks if any_mark else None)


def prepare(paths: List[str]) -> None:
    return None


def sort_key(rel: str) -> Tuple[int, str]:
    return group_priority(rel), rel


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    for tid, rows in iter_tables(path, lambda m: m.lower().endswith(".csv")):
        label = source_label(rel, tid)
        group = voltage_group(tid) or voltage_group(rel)
        block = parse_load_table(rows, label, group)
        if block is None:
            log.warning("no transformer columns in %s", label)
            continue
        yield block


# --- capacity ---------------------------------------------------------------------------------

_CLASS_SPLIT = re.compile(r"\s+")


def split_first_column(c: str) -> Tuple[str, str, str]:
    """'変東京都(23区) 配電用変電所 323' -> ('東京都(23区)', '配電用変電所', '323');
    '変基幹 275kV 1-1' -> ('', '基幹 275kV', '1-1')."""
    s = clean_label(c)
    if s.startswith("変"):
        s = s[1:]
    tokens = [t for t in _CLASS_SPLIT.split(s) if t]
    if len(tokens) < 2:
        return "", s, ""
    if tokens[0] == "基幹":
        return "", " ".join(tokens[:-1]), tokens[-1]
    return tokens[0], " ".join(tokens[1:-1]), tokens[-1]


# fixed positions in *_hendensyo.csv (checked against the header before use)
POS = {"name": 1, "kv": 2, "units": 3, "rated": 4, "operating": 5, "forecast": 10,
       "available": 11, "n1": 13}


def parse_capacity_table(rows, source: str) -> List[Dict[str, object]]:
    rows = [list(r) for r in rows]
    head = rows[:8]
    hdr_ok = any(len(r) > 3 and clean_label(r[1]) == "変電所名" and clean_label(r[3]) == "台数"
                 for r in head)
    if not hdr_ok:
        log.warning("unexpected header in %s", source)
        return []
    as_of = as_of_from(head, source)
    out = []
    for r in rows:
        if len(r) < 14 or not clean_label(r[0]).startswith("変"):
            continue
        name = clean_label(r[POS["name"]])
        if not name:
            continue
        area, pclass, number = split_first_column(r[0])
        kv = clean_label(r[POS["kv"]])
        v1, v2 = "", ""
        if "/" in kv:
            a, b = kv.split("/", 1)
            v1, v2 = norm_kv(a), norm_kv(b)
        elif kv:
            v1 = norm_kv(kv)
        rec = capacity_record(OPERATOR, name, number, v1, v2, r[POS["units"]], r[POS["rated"]],
                              r[POS["operating"]], r[POS["forecast"]], r[POS["available"]],
                              clean_label(r[POS["n1"]]), source, as_of, publisher_class=pclass)
        out.append(rec)
    return out


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for tid, rows in iter_tables(path, lambda m: "hendensyo" in m.lower()):
        out.extend(parse_capacity_table(rows, source_label(rel, tid)))
    return out
