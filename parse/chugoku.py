"""Chugoku Electric Power Transmission & Distribution.

Loading: jisseki_{kikan00,local10-50}_tr_YYYY_07.csv, common layout, names with the 変電所 suffix,
hour-ending timestamps. Distribution transformers (identifier containing H) are not published.
Capacity: csv_{220kv,tori,shima,oka,hiro,yama}.zip, members sys_capa_*_tr_*.csv (line members are
skipped). Some cells hold multi-line text; files are parsed with a CSV reader on the full text."""
from __future__ import annotations

from typing import Dict, Iterator, List, Optional

from . import generic
from .wide import Block

OPERATOR = "chugoku"


def prepare(paths: List[str]) -> Optional[object]:
    return None


def sort_key(rel: str):
    return rel


def load_blocks(path: str, rel: str, ctx=None) -> Iterator[Block]:
    return generic.load_blocks(path, rel)


def capacity_rows(path: str, rel: str) -> List[Dict[str, object]]:
    return generic.capacity_rows(path, rel, OPERATOR, lambda m: "_tr_" in m.lower())
