"""Generic parser for transformer capacity tables (予想潮流・空容量一覧, transformer sheet).

The common template has one header row containing (labels vary slightly between operators):
  変電所No | 変電所名 | 電圧(一次) | 電圧(二次) | 台数 | 設備容量(100%×台数) | 運用容量値 |
  運用容量制約要因 | 予想潮流 | 空容量(当該設備) | 空容量(上位系等考慮) | N-1電制適用可否 | ...
Columns are located by label. Rows with neither a primary nor a secondary voltage (footnotes,
trailing notes, blank lines) are dropped. Extra unquoted cells to the right of the header (lists of
upstream equipment spilling over several cells) are ignored.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .common import MISSING_TOKENS, clean_label, kv_value, norm_kv, parse_number
from .names import substation_key

CAPACITY_FIELDS = ["operator", "substation_raw", "substation_key", "v1_kv", "v2_kv", "category",
                   "publisher_class", "units", "rated_mw", "operating_mw", "forecast_flow_mw",
                   "available_mw_published", "n1_note", "source_file", "as_of"]

_DATE = re.compile(r"(20\d{2})年\s*(\d{1,2})月\s*(\d{1,2})日")
_YM_IN_NAME = re.compile(r"_(20\d{2})(\d{2})_\d+\.csv$", re.IGNORECASE)


def as_of_from(rows_head: List[Sequence], source_file: str) -> str:
    for r in rows_head:
        for c in r[:3] if r else []:
            m = _DATE.search(clean_label(c))
            if m:
                return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = _YM_IN_NAME.search(source_file)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return ""


def category_for(v2_kv: str, publisher_class: str = "") -> str:
    """Secondary-voltage class of a capacity row:
    distribution_6kV (secondary below 7 kV), subtransmission_7_33kV, transmission_44kV_plus,
    or voltage_unpublished (blank voltage; the publisher class is kept in publisher_class)."""
    v = kv_value(v2_kv)
    if v is None:
        return "voltage_unpublished"
    if v < 7.0:
        return "distribution_6kV"
    if v <= 33.0:
        return "subtransmission_7_33kV"
    return "transmission_44kV_plus"


def _locate(header: Sequence) -> Optional[Dict[str, int]]:
    labels = [clean_label(c) for c in header]
    col: Dict[str, int] = {}
    avail = []
    for j, lab in enumerate(labels):
        if not lab:
            continue
        if "sub_no" not in col and re.match(r"^(変電所\s*No|略号)", lab, re.IGNORECASE):
            col["sub_no"] = j
        elif "name" not in col and lab.startswith("変電所名"):
            col["name"] = j
        elif "v1" not in col and "一次" in lab:
            col["v1"] = j
        elif "v2" not in col and "二次" in lab:
            col["v2"] = j
        elif "units" not in col and lab.startswith("台数"):
            col["units"] = j
        elif "rated" not in col and "設備容量" in lab:
            col["rated"] = j
        elif "operating" not in col and "運用容量" in lab and "制約" not in lab:
            col["operating"] = j
        elif "forecast" not in col and "予想潮流" in lab:
            col["forecast"] = j
        elif "空容量" in lab or "空き容量" in lab:
            avail.append((j, lab))
        elif "n1" not in col and "N-1" in lab.upper() and "可否" in lab:
            col["n1"] = j
    if avail:
        own = [j for j, lab in avail if "当該" in lab]
        col["available"] = own[0] if own else avail[0][0]
    if "name" in col and "units" in col and ("v1" in col or "v2" in col):
        return col
    return None


_HEAD = re.compile(r"-?\d{1,3}")
_TAIL = re.compile(r"\d{3}\s*")


def _merge_region(row: List[object], start: int, actual: int, expected: int) -> List[object]:
    """Merge (shift = actual - expected) split numbers inside row[start:actual]."""
    shift = actual - expected
    while shift > 0:
        for k in range(actual - 2, start - 1, -1):
            a, b = row[k], row[k + 1]
            if (isinstance(a, str) and isinstance(b, str) and _HEAD.fullmatch(a)
                    and _TAIL.fullmatch(b)):
                row = row[:k] + [a + b.strip()] + row[k + 2:]
                actual -= 1
                shift -= 1
                break
        else:
            break
    return row


def repair_split_thousands(row: List[object], col: Dict[str, int]) -> List[object]:
    """Undo unquoted thousands separators that split one number over two cells
    (e.g. '2,1,425 ,784 ,熱容量' -> units 2, rated 1425, operating 784).

    The text column 運用容量制約要因 (just right of the operating capacity) is the anchor: if it is
    found k cells further right than the header says, k merges are made among the numeric cells
    to its left, choosing pairs whose left part has 1-3 digits without a trailing space and whose
    right part has exactly 3 digits. The N-1 applicability column (可 / 不可) anchors the numeric
    cells between the two in the same way. Rows whose anchors are where expected are unchanged."""
    if "operating" not in col:
        return row
    exp = col["operating"] + 1
    actual = None
    for k in range(exp, min(len(row), exp + 4)):
        s = clean_label(row[k])
        if s and s not in MISSING_TOKENS and parse_number(s) is None:
            actual = k
            break
    if actual is not None and actual > exp:
        row = _merge_region(row, col.get("units", exp - 3), actual, exp)
    if "n1" in col:
        exp2 = col["n1"]
        for k in range(exp2, min(len(row), exp2 + 4)):
            if "可" in clean_label(row[k]):
                if k > exp2:
                    row = _merge_region(row, exp + 1, k, exp2)
                break
    return row


def parse_capacity_rows(rows: Iterable[Sequence], operator: str, source_file: str,
                        max_header_rows: int = 30) -> List[Dict[str, object]]:
    it = iter(rows)
    head: List[Sequence] = []
    col = None
    for row in it:
        row = list(row)
        head.append(row)
        col = _locate(row)
        if col is not None or len(head) > max_header_rows:
            break
    if col is None:
        return []
    as_of = as_of_from(head, source_file)

    def get(row: Sequence, key: str):
        j = col.get(key)
        return row[j] if j is not None and j < len(row) else None

    out: List[Dict[str, object]] = []
    for row in it:
        row = repair_split_thousands(list(row), col)
        v1 = norm_kv(get(row, "v1"))
        v2 = norm_kv(get(row, "v2"))
        if not v1 and not v2:
            continue
        name = clean_label(get(row, "name"))
        sub_no = clean_label(get(row, "sub_no"))
        out.append(capacity_record(operator, name, sub_no, v1, v2, get(row, "units"),
                                   get(row, "rated"), get(row, "operating"),
                                   get(row, "forecast"), get(row, "available"),
                                   clean_label(get(row, "n1")), source_file, as_of))
    return out


def capacity_record(operator: str, name: str, sub_no: str, v1: str, v2: str, units, rated,
                    operating, forecast, available, n1_note: str, source_file: str, as_of: str,
                    publisher_class: str = "") -> Dict[str, object]:
    u = parse_number(units)
    key = substation_key(name) if name else ""
    return {
        "operator": operator,
        "substation_raw": name,
        "substation_key": key if key else (f"#{sub_no}" if sub_no else ""),
        "v1_kv": v1,
        "v2_kv": v2,
        "category": category_for(v2, publisher_class),
        "publisher_class": publisher_class,
        "units": int(u) if u is not None else None,
        "rated_mw": parse_number(rated),
        "operating_mw": parse_number(operating),
        "forecast_flow_mw": parse_number(forecast),
        "available_mw_published": parse_number(available),
        "n1_note": n1_note,
        "source_file": source_file,
        "as_of": as_of,
    }


def merge_split_rows(rows: List[Dict[str, object]]) -> Tuple[List[Dict[str, object]], int]:
    """Merge records that describe one transformer group printed on several lines of a table.

    Some operators print a transformer group on two lines of the same file (for example one line carrying
    the forecast flow and the next carrying the available capacity), or list the same group under two
    grid sections. Records from one source file with the same substation key, primary and secondary
    voltage, number of units, rated capacity and operating capacity are merged into one record; empty
    fields are filled from the later records. Returns the merged rows and the number of records removed.
    """
    sig_fields = ("operator", "source_file", "substation_key", "v1_kv", "v2_kv", "units", "rated_mw",
                  "operating_mw")
    first: Dict[Tuple, Dict[str, object]] = {}
    out: List[Dict[str, object]] = []
    removed = 0
    for r in rows:
        sig = tuple(str(r.get(f, "")) for f in sig_fields)
        if not r.get("substation_key") or sig not in first:
            if r.get("substation_key"):
                first[sig] = r
            out.append(r)
            continue
        keep = first[sig]
        for k, v in r.items():
            if keep.get(k) in (None, "") and v not in (None, ""):
                keep[k] = v
        removed += 1
    return out, removed
