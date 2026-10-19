"""Hokkaido Electric Power Network.

Loading:
- tide_results_transformer.zip: bulk-system transformers (187 kV and above), one CSV per fiscal
  year (jisseki_kikan01_tr_YYYY_01.csv); common wide layout with the name row last. Zip member
  names are CP932.
- tide_results_trans_NN.zip (NN = 01..24, local areas): one CSV per fiscal year
  (jisseki_localNN_linetr_YYYY_01.csv) mixing line and transformer columns. Label rows are
  設備No / 電圧 / 設備名 / 送電端 / 受電端. Transformer columns are those whose 設備名 contains
  変圧器 (e.g. '幌延変電所 連絡用変圧器'); the substation is the part of the name up to 変電所,
  primary/secondary voltage are the sending/receiving ends ('100kV' -> '100', '33kV' -> '33').
Capacity: sys_capa_kikan.zip and sys_capa_localNN.zip, member *_Tr_*.csv (common template; the
upstream-equipment list spills over extra unquoted cells, which are ignored).
"""
from __future__ import annotations

import re
from typing import Dict, Iterator, List, Optional, Sequence

from . import generic
from .common import clean_label, norm_kv
from .wide import Block, ColMeta, _cell

OPERATOR = "hokkaido"
_STATION = re.compile(r"^(.*?(?:変電所|開閉所|発電所))\s*(.*)$")


def prepare(paths: List[str]) -> Optional[object]:
    return None


def sort_key(rel: str):
    return rel


def linetr_col_builder(j: int, roles: Dict[str, Sequence]) -> Optional[ColMeta]:
    name = clean_label(_cell(roles.get("name", []), j))
    if "変圧器" not in name:
        return None
    sub_no = clean_label(_cell(roles.get("sub_no", []), j))
    m = _STATION.match(name)
    station, element = (m.group(1), m.group(2)) if m else (name, "")
    v1 = norm_kv(_cell(roles.get("send", []), j))
    v2 = norm_kv(_cell(roles.get("recv", []), j))
    return ColMeta(sub_no, station, v1, v2, f"{sub_no}:{element}" if element else sub_no)


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    def is_linetr(m: str) -> bool:
        return "_linetr_" in m.lower()

    for b in generic.load_blocks(path, rel, lambda m: m.lower().endswith(".csv") and not is_linetr(m)):
        yield b
    for b in generic.load_blocks(path, rel, lambda m: m.lower().endswith(".csv") and is_linetr(m),
                                 col_builder=linetr_col_builder):
        yield b


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR, lambda m: "_tr_" in m.lower())
