"""Tohoku Electric Power Network.

Loading: jisseki_{kikan01,local01-07}_tr_YYYY_02.csv (FY2022 onward) and ju-sohai_03-*.csv
(FY2020, FY2021). Common wide layout; cells carry a leading apostrophe; recent files are UTF-8
with BOM, older ones CP932; hour-ending timestamps (04-01 01:00 ... 04-01 00:00 of the next year).
Some columns carry only a number in the name row (the published name equals the No); those are
kept with an unjoinable key.
Capacity: sys_capa_{kikan01,local01-07}_tr_YYYYMM_02.csv, common template; the published
available-capacity column is mostly '-' and the publisher states it can be computed as
operating capacity minus the absolute forecast flow."""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from . import generic
from .wide import Block

OPERATOR = "tohoku"


def prepare(paths: List[str]) -> Optional[object]:
    return None


def sort_key(rel: str):
    return rel


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    return generic.load_blocks(path, rel)


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR)
