"""Hokuriku Electric Power Transmission & Distribution.

Loading: juyou{2019..2022}.csv (labels 変電所番号 / 名称; the transformer voltage is given in the
name, e.g. '中能登変電所(500kV)'), jisseki_{154ijou,local_<pref>}_tr_2023.csv (long preamble),
jisseki_{kikan01,local01-04}_tr_YYYY_05.csv. Names in local files carry voltage suffixes such as
'66/22kV' that are removed by the key normalisation.
Capacity: sys_capa_{kikan01,local01-03}_tr_YYYYMM_05.csv, common template."""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from . import generic
from .wide import Block

OPERATOR = "hokuriku"


def prepare(paths: List[str]) -> Optional[object]:
    return None


def sort_key(rel: str):
    return rel


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    return generic.load_blocks(path, rel)


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR)
