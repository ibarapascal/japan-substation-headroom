"""Facility-level greenhouse gas emission files of the national reporting system (EEGS).

The Ministry of the Environment publishes, per fiscal year, the emissions reported by every
facility under the mandatory reporting system (温室効果ガス排出量算定・報告・公表制度). The search page
offers a national download (prefecture code 000000) of the facility list:
  https://eegs.env.go.jp/ghg-santeikohyo-result/search/download?repYear=<FY>&prefectureCode=000000&emitterType=office
Each download is a zip holding search_result_<FY>/search_result_<FY>.csv (UTF-8 with BOM; columns
法人番号, 特定排出者コード, 事業者・事業所名, 区分, 業種, 所在地, 温室効果ガス算定排出量(tCO2), ページ).
Files are saved as RAW_DIR/national_office_<FY>.zip.
"""
from __future__ import annotations

import logging
import os
from typing import List

from .http import download_to

log = logging.getLogger("fetch.eegs")

URL = ("https://eegs.env.go.jp/ghg-santeikohyo-result/search/download"
       "?repYear={year}&prefectureCode=000000&emitterType=office")


def download(out: str, years: List[int]) -> int:
    os.makedirs(out, exist_ok=True)
    fails = 0
    for y in years:
        dest = os.path.join(out, f"national_office_{y}.zip")
        status, n, sha = download_to(URL.format(year=y), dest)
        log.info("FY%d HTTP %s %d bytes sha256=%s", y, status, n, sha)
        fails += status != 200
    return 1 if fails else 0
