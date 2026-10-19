"""Kyushu Electric Power Transmission and Distribution.

Loading: file names contain random segments and are resolved from the link text 潮流実績(変圧器).
- FY2024: jisseki_{kikan00,local00}_tr_YYYY_09.csv, common layout.
- FY2022-2023 local: CSV with a long preamble (one file's title reads 送電線 although the layout is
  the transformer layout); common layout.
- FY2020-2023 bulk: Excel (.xlsx; FY2020 .xls) with labels 変電所No (full width) / 変電所 /
  電圧一次 / 電圧二次. A station with two transformer groups occupies two columns of a merged
  name cell; the second column inherits the No and name. Timestamps are text 'YY/MM/DD HH'.
Capacity: one zip ("変圧器CSV") holding one CSV per area, common template.
"""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from . import generic
from .wide import Block

OPERATOR = "kyushu"


def prepare(paths: List[str]) -> Optional[object]:
    return None


def sort_key(rel: str):
    return rel


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    return generic.load_blocks(path, rel)


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR, lambda m: m.lower().endswith(".csv"))
