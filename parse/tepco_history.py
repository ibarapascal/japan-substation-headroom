"""TEPCO Power Grid archived capacity lists (akiyouryou_<area>.pdf, 2019-2025).

Until 2025 TEPCO published, per area, a PDF "運用容量一覧表" (operating capacity list) next to the
available-capacity map. The files are no longer linked from the operator's site; copies are held
by the Internet Archive. Each file holds, per voltage class, two tables:

  送電線 (lines):        No | name | kV | circuits | rated (100% x circuits) | operating capacity |
                          constraint | available (this equipment) | available (incl. upstream) |
                          N-1 applicability | N-1 applicable amount | [later files: output
                          control columns] | remarks
  変電所 (substations):  No | name | primary kV | secondary kV | units | rated | operating |
                          constraint | available | available (incl. upstream) | N-1 ... | remarks

and a "配電用変電所エリア運用容量一覧表" (distribution substation area list) with the substation
layout and the area number as No. Available capacity is published for connecting generation
(reverse-flow direction). This format has no forecast-flow column.

Parsing works on the text layer (pdftotext -layout), one line per table row:
  - section headers ("運用容量一覧表～ 154kV の特高設備 ～", "配電用変電所エリア運用容量一覧表") set
    the voltage class; column headers ("送電線名" / "変電所名") set the table type;
  - a data row starts with the area label (which may wrap onto the previous line), then the
    voltage class token ("154kV") and the row number, or, in distribution area tables, the area
    number; the name runs up to the first numeric token;
  - the cells after the name are read in their published order (positional mode). A row whose
    positional reading fails the checks (constraint cell is text, capacities are numeric or
    masked) is re-read around the constraint cell (anchor mode: rated, operating before it,
    available and available-incl.-upstream after it); rows that fail both are skipped and counted.
Masked cells ("-", "‑", "※", ...) are read as missing. Footnote marks (♯1, #2) are removed from
the N-1 applicability cell.

Known limits: names that wrap onto two text lines keep only the part on the row line; remarks
are not extracted.
"""
from __future__ import annotations

import datetime as dt
import re
import subprocess
from typing import Dict, Iterator, List, Optional, Tuple

from .common import nfkc
from .names import substation_key

HISTORY_FIELDS = [
    "snapshot_date", "capture_timestamp", "area", "area_label", "as_of", "data_basis_date",
    "table_type", "voltage_class", "row_no", "name", "name_key", "v1_kv", "v2_kv", "line_kv",
    "units", "rated_mw", "operating_mw", "constraint", "forecast_flow_mw",
    "available_mw_published", "available_upper_mw", "n1_applicable", "n1_mw", "parse_mode",
    "source_file",
]

AREAS = ["chiba", "fukushima", "gunma", "ibaraki", "kanagawa", "kikan", "nagano", "niigata",
         "saitama", "shizuoka", "tama", "tochigi", "tokyo23", "yamanashi"]

FILE_RE = re.compile(r"^akiyouryou_(?P<area>[a-z0-9]+)_(?P<ts>\d{14})\.pdf$")
MASK = {"", "-", "‑", "−", "―", "ー", "－", "‐", "–", "—", "※", "◇"}
CONSTRAINTS = {"熱容量", "電圧", "安定度", "系統安定度", "周波数", "短絡容量", "同期安定度",
               "電圧安定度", "過渡安定度"}
_NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
_INT = re.compile(r"^\d+$")
_ROWNO = re.compile(r"^\d+(?:-\d+)?$")
_KVTOK = re.compile(r"^(\d+)kV$")
_FOOT = re.compile(r"[♯#][0-9]*")
_DATE_JA = re.compile(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日")


def parse_file_name(name: str) -> Optional[Tuple[str, str, str]]:
    """'akiyouryou_chiba_20190726114923.pdf' -> ('chiba', '20190726114923', '2019-07-26')."""
    m = FILE_RE.match(name)
    if not m:
        return None
    ts = m.group("ts")
    return m.group("area"), ts, f"{ts[:4]}-{ts[4:6]}-{ts[6:8]}"


def pdf_text(path: str, timeout: int = 120) -> str:
    """Text layer of a PDF via pdftotext -layout (empty string when the PDF cannot be read)."""
    try:
        res = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", path, "-"],
                             capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    if res.returncode != 0:
        return ""
    return res.stdout.decode("utf-8", errors="replace")


def _num(t: str) -> Optional[float]:
    s = t.replace(",", "")
    if s in MASK:
        return None
    return float(s) if _NUM.match(s) else None


def _is_num(t: str) -> bool:
    return bool(_NUM.match(t.replace(",", "")))


def _is_num_or_mask(t: str) -> bool:
    return t in MASK or _is_num(t)


def _ja_date(s: str) -> str:
    m = _DATE_JA.search(s)
    if not m:
        return ""
    try:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3))).isoformat()
    except ValueError:
        return ""


def _clean_n1(tokens: List[str]) -> Tuple[str, List[str]]:
    """First N-1 applicability token without footnote marks, and the tokens after it
    (pure footnote tokens dropped)."""
    if not tokens:
        return "", []
    flag = _FOOT.sub("", tokens[0]).strip()
    rest = [t for t in tokens[1:] if _FOOT.sub("", t).strip() != ""]
    return flag, rest


def _fields_positional(table_type: str, cells: List[str]) -> Optional[Dict[str, object]]:
    """Cells after the name, in published order."""
    if table_type == "line":
        need = 7
        if len(cells) < need:
            return None
        kv, units, rated, oper, cons, avail, upper = cells[:7]
        v1 = v2 = ""
        line_kv = kv
        tail = cells[7:]
    else:
        need = 8
        if len(cells) < need:
            return None
        v1, v2, units, rated, oper, cons, avail, upper = cells[:8]
        line_kv = ""
        tail = cells[8:]
    if not (_is_num_or_mask(units) and _is_num_or_mask(rated) and _is_num_or_mask(oper)
            and _is_num_or_mask(avail) and _is_num_or_mask(upper)):
        return None
    if _is_num(cons):  # the constraint cell is text or masked
        return None
    if table_type != "line" and not (_is_num_or_mask(v1)):
        return None
    if table_type == "line" and not _is_num_or_mask(line_kv):
        return None
    n1, rest = _clean_n1(tail)
    n1_mw = rest[0] if rest else ""
    return {"v1": v1, "v2": v2, "line_kv": line_kv, "units": units, "rated": rated,
            "oper": oper, "cons": cons, "avail": avail, "upper": upper, "n1": n1,
            "n1_mw": n1_mw if _is_num_or_mask(n1_mw) else ""}


def _fields_anchor(table_type: str, cells: List[str]) -> Optional[Dict[str, object]]:
    """Re-read around a known constraint token. The cells before it are assigned from the left
    (line: kV, circuits, rated, operating; substation: primary kV, secondary kV, units, rated,
    operating); cells left blank by the publisher (non-disclosed capacities) are missing at the
    right end of that group."""
    for i in range(1, len(cells) - 2):
        if cells[i] in CONSTRAINTS and _is_num_or_mask(cells[i + 1]) \
                and _is_num_or_mask(cells[i + 2]):
            pre = cells[:i]
            names = (["line_kv", "units", "rated", "oper"] if table_type == "line"
                     else ["v1", "v2", "units", "rated", "oper"])
            if len(pre) > len(names) or not all(_is_num_or_mask(t) for t in pre):
                return None
            out = {"v1": "", "v2": "", "line_kv": "", "units": "", "rated": "", "oper": ""}
            out.update(dict(zip(names, pre)))
            n1, rest = _clean_n1(cells[i + 3:])
            n1_mw = rest[0] if rest else ""
            out.update({"cons": cells[i], "avail": cells[i + 1], "upper": cells[i + 2],
                        "n1": n1, "n1_mw": n1_mw if _is_num_or_mask(n1_mw) else ""})
            return out
    return None


def _split_row(tokens: List[str], distribution: bool) -> Optional[Tuple[str, str, int]]:
    """(voltage_class, row_no, index of the first name token) for a data row, else None."""
    for k in range(0, min(4, len(tokens) - 2)):
        m = _KVTOK.match(tokens[k])
        if m and _ROWNO.match(tokens[k + 1]):
            return f"{m.group(1)}kV", tokens[k + 1], k + 2
    if distribution:
        for k in range(0, min(4, len(tokens) - 2)):
            if _INT.match(tokens[k]) and all(not _is_num(t) for t in tokens[:k]) \
                    and not _is_num(tokens[k + 1]):
                return "distribution_area", tokens[k], k + 1
    return None


_FUSED = re.compile(r"^(\d+)([^\d\-.,].*)$")


def _unfuse(tokens: List[str]) -> List[str]:
    """Split a row number printed without a space before the name ('146長作線')."""
    for k in range(0, min(4, len(tokens) - 1)):
        if _KVTOK.match(tokens[k]):
            m = _FUSED.match(tokens[k + 1])
            if m:
                return tokens[:k + 1] + [m.group(1), m.group(2)] + tokens[k + 2:]
            break
    return tokens


def _kv_text(t: str) -> str:
    t = t.replace("以下", "")
    return t if _is_num(t) else ""


def parse_text(text: str, area: str, capture_ts: str, snapshot_date: str,
               source_file: str) -> Tuple[List[Dict[str, object]], Dict[str, int]]:
    """Rows of one archived capacity list, and counters (rows, positional, anchor, skipped)."""
    text = nfkc(text)
    as_of = ""
    basis = ""
    m = re.search(r"資料作成日\s*(\d{4}年\s*\d{1,2}月\s*\d{1,2}日)", text)
    if m:
        as_of = _ja_date(m.group(1))
    m = re.search(r"(\d{4}年\s*\d{1,2}月\s*\d{1,2}日)\s*時点", text)
    if m:
        basis = _ja_date(m.group(1))
    rows: List[Dict[str, object]] = []
    stats = {"rows": 0, "positional": 0, "anchor": 0, "skipped": 0}
    vclass = ""
    distribution = False
    ttype = ""
    label = ""
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            continue
        if "運用容量一覧表" in s and "留意" not in s and "について" not in s:
            distribution = "配電用変電所エリア" in s
            mk = re.search(r"(\d+)\s*kV", s)
            vclass = "distribution_area" if distribution else (f"{mk.group(1)}kV" if mk else "")
            label = s.split("運用容量一覧表")[0].replace("配電用変電所エリア", "").strip()
            ttype = "distribution_area" if distribution else ""
            continue
        if not distribution and ("送電線名" in s or "変電所名" in s):
            ttype = "line" if "送電線名" in s else "substation"
            continue
        if not ttype:
            continue
        tokens = _unfuse(s.split())
        if len(tokens) < 8:
            continue
        sp = _split_row(tokens, distribution)
        if sp is None:
            continue
        row_vclass, row_no, i0 = sp
        j = i0
        while j < len(tokens) and not _is_num_or_mask(tokens[j]):
            j += 1
        if j == i0 and _is_num(tokens[i0]):  # facility published under a number only
            j = i0 + 1
        name = "".join(tokens[i0:j])
        if not name or j >= len(tokens):
            stats["skipped"] += 1
            continue
        cells = tokens[j:]
        kind = "line" if ttype == "line" else "substation"
        f = _fields_positional(kind, cells)
        mode = "positional"
        if f is None:
            f = _fields_anchor(kind, cells)
            mode = "anchor"
        if f is None:
            stats["skipped"] += 1
            continue
        stats[mode] += 1
        stats["rows"] += 1
        rows.append({
            "snapshot_date": snapshot_date, "capture_timestamp": capture_ts, "area": area,
            "area_label": label, "as_of": as_of, "data_basis_date": basis,
            "table_type": ttype, "voltage_class": row_vclass, "row_no": row_no,
            "name": name, "name_key": substation_key(name),
            "v1_kv": _kv_text(str(f["v1"])), "v2_kv": _kv_text(str(f["v2"])),
            "line_kv": _kv_text(str(f["line_kv"])),
            "units": _num(str(f["units"])), "rated_mw": _num(str(f["rated"])),
            "operating_mw": _num(str(f["oper"])),
            "constraint": "" if f["cons"] in MASK else f["cons"],
            "forecast_flow_mw": None,
            "available_mw_published": _num(str(f["avail"])),
            "available_upper_mw": _num(str(f["upper"])),
            "n1_applicable": "" if f["n1"] in MASK else f["n1"],
            "n1_mw": _num(str(f["n1_mw"])), "parse_mode": mode, "source_file": source_file,
        })
    return rows, stats


def parse_pdf(path: str, file_name: str) -> Tuple[List[Dict[str, object]], Dict[str, int], bool]:
    """(rows, counters, readable) for one archived PDF."""
    meta = parse_file_name(file_name)
    if meta is None:
        return [], {"rows": 0, "positional": 0, "anchor": 0, "skipped": 0}, False
    area, ts, date = meta
    text = pdf_text(path)
    if len(text) < 500:
        return [], {"rows": 0, "positional": 0, "anchor": 0, "skipped": 0}, False
    rows, stats = parse_text(text, area, ts, date, file_name)
    return rows, stats, True


def iter_pdfs(raw: str) -> Iterator[Tuple[str, str]]:
    """(path, file name) of archived capacity lists below RAW, sorted by capture time."""
    import os
    found = []
    for root, _d, files in os.walk(raw):
        for fn in files:
            meta = parse_file_name(fn)
            if meta:
                found.append((meta[1], meta[0], os.path.join(root, fn), fn))
    for _ts, _a, path, fn in sorted(found):
        yield path, fn
