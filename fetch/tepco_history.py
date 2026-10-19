"""Archived TEPCO capacity lists (akiyouryou_<area>.pdf, 2019-2025) from the Internet Archive.

The operator published one capacity-list PDF per area at
  https://www.tepco.co.jp/pg/consignment/system/pdf_new/akiyouryou_<area>.pdf
and stopped publishing them in this form in 2025. The captures used for the published build are
listed in tepco_history_snapshots.csv (local file name, size, SHA-256). The local file name is
akiyouryou_<area>_<capture timestamp>.pdf, so the Wayback URL is reconstructed from it.
Captures are de-duplicated by content: a file identical to an earlier capture of the same area is
not listed.

Usage:
  python -m fetch history --out RAW_DIR [--areas chiba,kikan] [--interval 5]

Files are written to RAW_DIR/tepco_capacity_history/<YYYYMMDD>/ and skipped when already present
with the listed SHA-256. Some captures are stored by the Internet Archive truncated at 1,048,576
bytes and cannot be read; they are listed and downloaded like the others.
"""
from __future__ import annotations

import csv
import logging
import os
from typing import Dict, List, Optional

from .http import download_to, sha256_file

log = logging.getLogger("fetch.history")

ORIGIN = "https://www.tepco.co.jp/pg/consignment/system/pdf_new/"
SNAPSHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tepco_history_snapshots.csv")


def original_url(area: str) -> str:
    return f"{ORIGIN}akiyouryou_{area}.pdf"


def _parts(file_name: str) -> Optional[tuple]:
    stem = file_name[:-4] if file_name.endswith(".pdf") else file_name
    bits = stem.split("_")
    if len(bits) != 3 or bits[0] != "akiyouryou" or len(bits[2]) != 14:
        return None
    return bits[1], bits[2]


def wayback_url(file_name: str, raw_bytes: bool = False) -> str:
    """Wayback URL of a capture; raw_bytes=True asks for the unmodified capture (id_)."""
    p = _parts(file_name)
    if p is None:
        return ""
    area, ts = p
    return f"https://web.archive.org/web/{ts}{'id_' if raw_bytes else ''}/{original_url(area)}"


def load_snapshots(path: str = SNAPSHOTS) -> List[Dict[str, str]]:
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def download(out: str, areas: Optional[List[str]] = None, interval: float = 5.0) -> int:
    base = os.path.join(out, "tepco_capacity_history")
    n_new = n_skip = n_fail = 0
    for s in load_snapshots():
        p = _parts(s["file_name"])
        if p is None or (areas and p[0] not in areas):
            continue
        dest = os.path.join(base, p[1][:8], s["file_name"])
        if os.path.exists(dest) and sha256_file(dest) == s["sha256"]:
            n_skip += 1
            continue
        status, n, sha = download_to(wayback_url(s["file_name"], raw_bytes=True), dest,
                                     min_interval=interval)
        if status != 200:
            log.warning("HTTP %s %s", status, s["file_name"])
            n_fail += 1
            continue
        if sha != s["sha256"]:
            log.warning("sha256 differs from the listed capture: %s", s["file_name"])
        n_new += 1
        log.info("%s %d bytes", s["file_name"], n)
    log.info("history: %d downloaded, %d already present, %d failed", n_new, n_skip, n_fail)
    return 0 if n_fail == 0 else 1
