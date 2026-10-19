"""End-to-end build on a tiny raw directory assembled from the fixtures."""
import csv
import os
import shutil

from conftest import FIXTURES
from pipeline.__main__ import build

LAYOUT = {
    "kansai/load_tr/01_chouryu_Tr_2024.csv": "kansai_load_less.csv",
    "kansai/capacity_tr/154kv_less_trans.csv": "kansai_capacity.csv",
    "tepco/load_tr/tyouryu_66kV.zip": "tepco_load_66kV.zip",
    "tepco/capacity_tr/csv_yosochoryu_tokyo.zip": "tepco_capacity.zip",
    "chubu/load_tr/rule_92.xlsx": "chubu_load_new.xlsx",
}


def read(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


import pytest


@pytest.mark.parametrize("fmt", ["auto", "csv"])
def test_build_end_to_end(tmp_path, fmt):
    raw = tmp_path / "raw"
    for dst, src in LAYOUT.items():
        os.makedirs(raw / os.path.dirname(dst), exist_ok=True)
        shutil.copy(os.path.join(FIXTURES, src), raw / dst)
    out = tmp_path / "out"
    assert build(str(raw), str(out), ["kansai", "tepco", "chubu"], fmt, None, False) == 0
    st = read(out / "stats" / "substation_year_stats.csv")
    assert {r["operator"] for r in st} == {"kansai", "tepco", "chubu"}
    head = read(out / "headroom" / "headroom_reconstructed.csv")
    kansai_matched = [r for r in head if r["operator"] == "kansai" and r["join_status"] == "matched_key_v2"]
    assert kansai_matched and all(r["headroom_naive_mw"] != "" for r in kansai_matched)
    assert any(r["join_status"] == "no_capacity_table" for r in head if r["operator"] == "chubu")
    rep = read(out / "headroom" / "join_report.csv")
    assert {r["operator"] for r in rep} == {"kansai", "tepco", "chubu"}
    assert any(f.startswith("kansai") for f in os.listdir(out / "load_long"))
    assert not os.path.exists(out / "_work")
