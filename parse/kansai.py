"""Kansai Transmission and Distribution.

Loading: 01_chouryu_Tr_YYYY_154more.csv (154 kV and above) and 01_chouryu_Tr_YYYY.csv (below
154 kV; FY2018-2021 files cover all levels). The first row of the below-154 kV file is a note,
the identifier label is 略号 / 変電所No, full-width identifiers; missing values are empty cells.
Capacity: 154kv_more_trans.csv / 154kv_less_trans.csv (quoted CSV, common template)."""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from . import generic
from .wide import Block

OPERATOR = "kansai"


def prepare(paths: List[str]) -> Optional[object]:
    return None


def sort_key(rel: str):
    return rel


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    return generic.load_blocks(path, rel)


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR)
