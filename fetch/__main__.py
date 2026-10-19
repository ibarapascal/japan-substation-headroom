"""Command line entry for the downloader.

Usage:
  python -m fetch download --out RAW_DIR [--operators tepco,kansai] [--refresh]
  python -m fetch list [--operators ...]            # resolve links only, download nothing
  python -m fetch archive --out RAW_DIR [--interval 5]   # archived TEPCO loading zips (Wayback)
  python -m fetch ingest-archive --out RAW_DIR [--subdir tepco_history]
  python -m fetch history --out RAW_DIR [--areas chiba,kikan]   # archived capacity lists
  python -m fetch eegs --out RAW_DIR [--years 2021,2022,2023]    # facility-level GHG files

download is idempotent: a file already present whose sha256 equals the manifest entry is skipped.
Entry pages are saved under RAW_DIR/<operator>/_pages/ so link resolution can be audited later.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import posixpath
import sys
from typing import Dict, List

from . import archive, manifest
from .http import download_to, get_bytes, sha256_file
from .sources import OPERATORS, SOURCES, Target, select_targets

log = logging.getLogger("fetch")


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _decode_html(body: bytes) -> str:
    for enc in ("utf-8", "cp932", "euc-jp"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def resolve(operator: str, raw_dir: str = "") -> List[Target]:
    targets: List[Target] = []
    for i, page in enumerate(SOURCES[operator].pages):
        status, body, final_url = get_bytes(page)
        if status != 200:
            log.warning("%s entry page %s -> HTTP %s", operator, page, status)
            continue
        if raw_dir:
            p = os.path.join(raw_dir, operator, "_pages", f"page{i}.html")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(body)
        targets.extend(select_targets(operator, final_url, _decode_html(body)))
    # unique local names: if two URLs share a basename, suffix the later ones
    seen: Dict[str, int] = {}
    uniq: List[Target] = []
    urls = set()
    for t in targets:
        if t.url in urls:
            continue
        urls.add(t.url)
        if t.local_name in seen:
            seen[t.local_name] += 1
            stem, ext = posixpath.splitext(t.local_name)
            t.local_name = f"{stem}__{seen[t.local_name]}{ext}"
        else:
            seen[t.local_name] = 0
        uniq.append(t)
    return uniq


def cmd_list(ops: List[str]) -> int:
    for op in ops:
        ts = resolve(op)
        print(f"== {op}: {len(ts)} targets")
        for t in ts:
            print(f"  {t.kind:12s} {t.local_name}  <- {t.url}  [{t.note}]")
        for kind, url, status in SOURCES[op].unpublished:
            print(f"  {kind:12s} (none) {status} {url}")
    return 0


def cmd_download(raw_dir: str, ops: List[str], refresh: bool) -> int:
    os.makedirs(raw_dir, exist_ok=True)
    mpath = os.path.join(raw_dir, "manifest.csv")
    rows = manifest.load(mpath)
    failures = 0
    for op in ops:
        try:
            targets = resolve(op, raw_dir)
        except Exception as e:  # keep going with other operators
            log.error("%s: entry page resolution failed: %s", op, e)
            failures += 1
            continue
        log.info("%s: %d targets", op, len(targets))
        for kind, url, status in SOURCES[op].unpublished:
            manifest.upsert(rows, {"operator": op, "kind": kind, "url": url, "local_name": "",
                                   "bytes": "", "sha256": "", "retrieved_at_utc": _now(),
                                   "http_status": status, "note": ""})
        for t in targets:
            dest = os.path.join(raw_dir, t.local_name)
            prev = rows.get(t.local_name)
            if (not refresh and prev and prev.get("sha256") and os.path.exists(dest)
                    and sha256_file(dest) == prev["sha256"]):
                log.info("skip (sha256 matches manifest) %s", t.local_name)
                continue
            try:
                status, n, sha = download_to(t.url, dest)
            except Exception as e:
                log.error("FAILED %s: %s", t.url, e)
                status, n, sha = "error", 0, ""
                failures += 1
            log.info("%s %s %s bytes", status, t.local_name, n)
            manifest.upsert(rows, {"operator": op, "kind": t.kind, "url": t.url,
                                   "local_name": t.local_name if n else "",
                                   "bytes": n, "sha256": sha, "retrieved_at_utc": _now(),
                                   "http_status": status, "note": t.note})
            manifest.save(mpath, rows)  # persist progress after every file
        manifest.save(mpath, rows)
    log.info("done; failures=%d; manifest=%s", failures, mpath)
    return 1 if failures else 0


def main(argv: List[str] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m fetch")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("download", "list", "ingest-archive"):
        s = sub.add_parser(name)
        s.add_argument("--operators", default=",".join(OPERATORS))
        if name != "list":
            s.add_argument("--out", required=True, help="raw directory for this retrieval")
        if name == "download":
            s.add_argument("--refresh", action="store_true")
        if name == "ingest-archive":
            s.add_argument("--subdir", default="tepco_history")
    w = sub.add_parser("archive", help="archived TEPCO hourly loading zips (Internet Archive)")
    w.add_argument("--out", required=True)
    w.add_argument("--interval", type=float, default=5.0, help="seconds between requests")
    w.add_argument("--expected", default=os.path.join("data", "manifest.csv"),
                   help="manifest whose SHA-256 values are checked (default: data/manifest.csv)")
    h = sub.add_parser("history", help="archived TEPCO capacity lists (Internet Archive)")
    h.add_argument("--out", required=True)
    h.add_argument("--areas", default="", help="comma-separated area ids (default: all)")
    h.add_argument("--interval", type=float, default=5.0, help="seconds between requests")
    e = sub.add_parser("eegs", help="national facility-level GHG emission files (EEGS)")
    e.add_argument("--out", required=True)
    e.add_argument("--years", default="2021,2022,2023")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stdout)
    if a.cmd == "archive":
        return archive.download(a.out, interval=a.interval,
                                expected=archive.expected_from_manifest(a.expected))
    if a.cmd == "history":
        from . import tepco_history
        areas = [x.strip() for x in a.areas.split(",") if x.strip()]
        return tepco_history.download(a.out, areas or None, a.interval)
    if a.cmd == "eegs":
        from . import eegs
        return eegs.download(a.out, [int(y) for y in a.years.split(",") if y.strip()])
    ops =[o.strip() for o in a.operators.split(",") if o.strip()]
    bad = [o for o in ops if o not in SOURCES]
    if bad:
        ap.error(f"unknown operators: {bad}")
    if a.cmd == "list":
        return cmd_list(ops)
    if a.cmd == "download":
        return cmd_download(a.out, ops, a.refresh)
    n = archive.ingest(a.out, a.subdir)
    log.info("registered %d archived files", n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
