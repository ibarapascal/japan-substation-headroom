"""Hourly transformer loading and capacity table parsers, one module per operator.

Every operator module exposes:
  OPERATOR                       operator id
  prepare(paths) -> ctx          optional pre-pass over that operator's loading files
  sort_key(rel)                  processing order of loading files
  load_blocks(path, rel, ctx)    -> iterator of wide.Block (hourly loading tables)
  capacity_rows(path, rel)       -> list of capacity records (see capacity.CAPACITY_FIELDS)
"""
from __future__ import annotations

from importlib import import_module

OPERATOR_IDS = ["hokkaido", "tohoku", "tepco", "chubu", "hokuriku", "kansai", "chugoku",
                "shikoku", "kyushu", "okinawa"]


def operator_module(op: str):
    if op not in OPERATOR_IDS:
        raise KeyError(op)
    return import_module(f"{__name__}.{op}")
