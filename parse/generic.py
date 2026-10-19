"""Default per-file entry points used by most operator modules."""
from __future__ import annotations

import logging
from typing import Callable, Dict, Iterator, List, Optional

from .capacity import parse_capacity_rows
from .tables import iter_tables, source_label
from .wide import Block, parse_wide_rows

log = logging.getLogger(__name__)


def load_blocks(path: str, rel: str, member_filter: Optional[Callable[[str], bool]] = None,
                col_builder=None) -> Iterator[Block]:
    for tid, rows in iter_tables(path, member_filter):
        label = source_label(rel, tid)
        block = parse_wide_rows(rows, label, col_builder)
        if block is None:
            log.warning("no transformer table recognised in %s", label)
            continue
        yield block


def capacity_rows(path: str, rel: str, operator: str,
                  member_filter: Optional[Callable[[str], bool]] = None) -> List[Dict[str, object]]:
    out: List[Dict[str, object]] = []
    for tid, rows in iter_tables(path, member_filter):
        label = source_label(rel, tid)
        recs = parse_capacity_rows(rows, operator, label)
        if not recs:
            log.warning("no capacity table recognised in %s", label)
        out.extend(recs)
    return out
