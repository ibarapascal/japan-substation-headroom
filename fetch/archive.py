"""Archived copies of TEPCO hourly loading zips: download from the Internet Archive and register.

Older fiscal years are no longer linked from the operator's page. `download` fetches the captures
listed in WAYBACK below into <raw>/tepco_history/wayback/ and then calls `ingest`, which records
every zip under <raw>/tepco_history/ in the manifest. The Wayback URL is reconstructed from the
file name (<original-stem>_<YYYYMMDD>.zip) using the table below, which lists the capture
timestamps of the original files; unknown names are recorded as archived_copy.

Usage:
  python -m fetch archive --out RAW_DIR [--interval 5]     # download + register
  python -m fetch ingest-archive --out RAW_DIR             # register files placed by hand
"""
from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Dict, Optional, Tuple

from . import manifest
from .http import download_to, sha256_file

log = logging.getLogger("fetch.archive")

ORIGIN = "https://www.tepco.co.jp/pg/consignment/system/pdf/"

# local file name -> (wayback capture timestamp, original file name)
WAYBACK: Dict[str, Tuple[str, str]] = {
    "tyouryuuzisseki_20190817.zip": ("20190817044620", "tyouryuuzisseki.zip"),
    "tyouryuuzisseki_20220420.zip": ("20220420084636", "tyouryuuzisseki.zip"),
    "tyouryuuzisseki2020_20220420.zip": ("20220420084550", "tyouryuuzisseki2020.zip"),
    "tyouryuuzisseki2021_20240209.zip": ("20240209033737", "tyouryuuzisseki2021_0805.zip"),
    "66kVtide_etc_20220119.zip": ("20220119140622", "66kVtide_etc.zip"),
    "tyouryu_154kV_20250118.zip": ("20250118093740", "tyouryu_154kV.zip"),
}


def wayback_url(name: str, raw_bytes: bool = False) -> str:
    """Wayback URL of a listed capture; raw_bytes=True asks for the unmodified capture (id_)."""
    if name in WAYBACK:
        ts, orig = WAYBACK[name]
        return f"https://web.archive.org/web/{ts}{'id_' if raw_bytes else ''}/{ORIGIN}{orig}"
    return "archived_copy"


def download(raw_dir: str, subdir: str = "tepco_history/wayback", interval: float = 5.0,
             expected: Optional[Dict[str, str]] = None) -> int:
    """Download the captures in WAYBACK into RAW_DIR/<subdir>/ and register them in the manifest.

    expected maps a file name to its SHA-256 (e.g. from the released data/manifest.csv); a file
    already present with that checksum is skipped, and a differing download is reported.
    Returns 0 when every capture is present afterwards, 1 otherwise.
    """
    expected = expected or {}
    base = os.path.join(raw_dir, subdir)
    fails = 0
    for name in sorted(WAYBACK):
        dest = os.path.join(base, name)
        want = expected.get(name, "")
        if os.path.exists(dest) and (not want or sha256_file(dest) == want):
            log.info("skip (present) %s", name)
            continue
        status, n, sha = download_to(wayback_url(name, raw_bytes=True), dest, min_interval=interval)
        if status != 200:
            log.warning("HTTP %s %s", status, name)
            fails += 1
            continue
        if want and sha != want:
            log.warning("sha256 differs from the released manifest: %s", name)
        log.info("%s %d bytes", name, n)
    top = subdir.split("/")[0]
    log.info("registered %d archived files", ingest(raw_dir, top))
    return 1 if fails else 0


def expected_from_manifest(path: str) -> Dict[str, str]:
    """File name -> SHA-256 of the archived copies listed in a manifest (missing file: empty)."""
    if not os.path.exists(path):
        return {}
    return {os.path.basename(r["local_name"]): r["sha256"]
            for r in manifest.load(path).values()
            if r["local_name"].startswith("tepco_history/") and r["sha256"]}


def ingest(raw_dir: str, subdir: str = "tepco_history", operator: str = "tepco") -> int:
    base = os.path.join(raw_dir, subdir)
    mpath = os.path.join(raw_dir, "manifest.csv")
    rows = manifest.load(mpath)
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    n = 0
    for root, _dirs, files in os.walk(base):
        for fn in sorted(files):
            if not fn.lower().endswith(".zip"):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, raw_dir)
            url = wayback_url(fn)
            manifest.upsert(rows, {
                "operator": operator, "kind": "load_tr", "url": url, "local_name": rel,
                "bytes": os.path.getsize(p), "sha256": sha256_file(p),
                "retrieved_at_utc": now, "http_status": "archived",
                "note": "archived copy of a file no longer linked from the operator page"
                        if url != "archived_copy" else
                        "archived copy of a file retrieved from the operator page earlier",
            })
            n += 1
    manifest.save(mpath, rows)
    return n
