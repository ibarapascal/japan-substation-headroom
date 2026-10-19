"""manifest.csv read/merge/write. One row per local file (or per unpublished item)."""
from __future__ import annotations

import csv
import os
from typing import Dict, List

FIELDS = ["operator", "kind", "url", "local_name", "bytes", "sha256",
          "retrieved_at_utc", "http_status", "note"]


def _key(row: Dict[str, str]) -> str:
    return row["local_name"] or f"{row['operator']}|{row['kind']}|{row['url']}"


def load(path: str) -> Dict[str, Dict[str, str]]:
    rows: Dict[str, Dict[str, str]] = {}
    if os.path.exists(path):
        with open(path, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                r = {k: (r.get(k) or "") for k in FIELDS}
                rows[_key(r)] = r
    return rows


def save(path: str, rows: Dict[str, Dict[str, str]]) -> None:
    tmp = path + ".tmp"
    ordered: List[Dict[str, str]] = sorted(
        rows.values(), key=lambda r: (r["operator"], r["kind"], r["local_name"], r["url"]))
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for r in ordered:
            w.writerow({k: r.get(k, "") for k in FIELDS})
    os.replace(tmp, path)


def upsert(rows: Dict[str, Dict[str, str]], row: Dict[str, str]) -> None:
    row = {k: str(row.get(k, "")) for k in FIELDS}
    rows[_key(row)] = row
