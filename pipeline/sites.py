"""Build the data center site register.

Usage:
  python -m pipeline sites --eegs EEGS_DIR --out OUT_DIR

EEGS_DIR holds national_office_<FY>.zip for FY2021-FY2023 (python -m fetch eegs). Curated inputs
are read from sites/ (see derive/dc_sites.py).

Output: OUT_DIR/sites/data_center_sites.csv
"""
from __future__ import annotations

import csv
import logging
import os

from derive.dc_sites import SITE_FIELDS, build_register

log = logging.getLogger("pipeline.sites")


def build_sites(eegs_dir: str, out: str) -> int:
    rows, stats = build_register(eegs_dir)
    odir = os.path.join(out, "sites")
    os.makedirs(odir, exist_ok=True)
    with open(os.path.join(odir, "data_center_sites.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SITE_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SITE_FIELDS})
    log.info("sites: %s", stats)
    return 0
