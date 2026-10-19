"""Shikoku Electric Power Transmission & Distribution.

Loading: jisseki_{kikan01,local01-04}_tr_YYYY_08.csv, tr_chouryu_YYYY.csv (bulk system,
FY2019-2023) and tr_chouryu_<pref>_YYYY.csv (local, FY2022-2023). Results are aggregated per
secondary bus by the publisher. Missing values are written as '－' or '―'. One secondary-voltage
cell holds a composite value with an embedded comma (e.g. '110,66'); the CSV reader keeps it in
one cell and the voltage is stored as '110/66'. One FY2022 local file carries a line-file title
but a transformer layout; it is parsed by layout.
Capacity: sys_capa_{kikan00,local01-04}_tr_YYYYMM_08.csv. Numbers with an unquoted thousands
separator (e.g. 1,425) split into two cells; see capacity.repair_split_thousands."""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from . import generic
from .wide import Block

OPERATOR = "shikoku"


def prepare(paths: List[str]) -> Optional[object]:
    return None


def sort_key(rel: str):
    return rel


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    return generic.load_blocks(path, rel)


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR)
