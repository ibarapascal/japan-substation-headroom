"""Archived TEPCO capacity lists: text-layer parser, file names, URLs, summary."""
import os

from conftest import FIXTURES
from fetch.tepco_history import load_snapshots, original_url, wayback_url
from parse.tepco_history import parse_file_name, parse_text
from pipeline.history import summarise


def parts():
    with open(os.path.join(FIXTURES, "tepco_history_excerpt.txt"), encoding="utf-8") as f:
        return f.read().split("========")


def rows_of(i, area="chiba"):
    rows, stats = parse_text(parts()[i], area, "20190726114923", "2019-07-26", "x.pdf")
    return rows, stats


def one(rows, **kw):
    hit = [r for r in rows if all(r[k] == v for k, v in kw.items())]
    assert len(hit) == 1, (kw, hit)
    return hit[0]


def test_file_name_and_urls():
    assert parse_file_name("akiyouryou_chiba_20190726114923.pdf") == \
        ("chiba", "20190726114923", "2019-07-26")
    assert parse_file_name("chiba_yosochoryu.pdf") is None
    assert original_url("chiba").endswith("/pdf_new/akiyouryou_chiba.pdf")
    assert wayback_url("akiyouryou_chiba_20190726114923.pdf") == (
        "https://web.archive.org/web/20190726114923/"
        "https://www.tepco.co.jp/pg/consignment/system/pdf_new/akiyouryou_chiba.pdf")
    assert "20190726114923id_/" in wayback_url("akiyouryou_chiba_20190726114923.pdf", True)


def test_snapshot_list_is_consistent():
    snaps = load_snapshots()
    assert len(snaps) == len({s["file_name"] for s in snaps})
    assert all(parse_file_name(s["file_name"]) and len(s["sha256"]) == 64 for s in snaps)


def test_dates_and_tables():
    rows, stats = rows_of(0)
    assert stats["skipped"] == 0
    r = one(rows, table_type="line", voltage_class="154kV", row_no="1")
    assert r["as_of"] == "2019-07-26" and r["data_basis_date"] == "2019-07-23"
    assert r["area_label"] == "千葉県"
    assert (r["name"], r["line_kv"], r["units"], r["rated_mw"], r["operating_mw"]) == \
        ("東葛線1・2L", "154", 2, 514, 290)
    assert (r["available_mw_published"], r["available_upper_mw"], r["n1_applicable"], r["n1_mw"]) \
        == (257, 0, "可", 224)
    assert r["forecast_flow_mw"] is None
    s = one(rows, table_type="substation", voltage_class="154kV", row_no="1")
    assert (s["name"], s["v1_kv"], s["v2_kv"], s["units"], s["available_mw_published"]) == \
        ("新野田11-14B", "275", "154", 4, 1254)


def test_fused_row_number_masks_and_footnotes():
    rows, _ = rows_of(0)
    r = one(rows, voltage_class="66kV", row_no="146")
    assert (r["name"], r["rated_mw"], r["available_mw_published"]) == ("長作線", 236, 118)
    t = one(rows, voltage_class="22kV", name="橘")
    assert t["n1_applicable"] == "不可" and t["n1_mw"] is None
    m = one(rows, voltage_class="22kV", name="溝原")
    assert (m["v1_kv"], m["v2_kv"], m["rated_mw"], m["constraint"], m["available_mw_published"]) \
        == ("22", "", None, "", 0)


def test_distribution_area_rows():
    rows, _ = rows_of(0)
    d = [r for r in rows if r["table_type"] == "distribution_area"]
    assert [r["row_no"] for r in d] == ["1", "2", "3", "22"]
    r = one(d, name="印西")
    assert (r["v1_kv"], r["v2_kv"], r["units"], r["rated_mw"], r["operating_mw"],
            r["available_mw_published"]) == ("66", "6.6", 3, 47, 49, 10)
    assert r["parse_mode"] == "positional"


def test_blank_capacities_read_in_anchor_mode():
    rows, stats = rows_of(1, "kikan")
    assert stats["rows"] == 3 and stats["anchor"] == 1
    r = one(rows, row_no="55")
    assert (r["name"], r["line_kv"], r["units"], r["rated_mw"], r["operating_mw"],
            r["available_mw_published"], r["parse_mode"]) == \
        ("中東京幹線", "275", 2, None, None, 0, "anchor")
    assert one(rows, row_no="1")["rated_mw"] == 13164


def test_numeric_name_and_masked_layout():
    rows, stats = rows_of(2, "tama")
    assert stats["skipped"] == 0
    r = one(rows, voltage_class="22kV", row_no="9")
    assert (r["name"], r["v1_kv"], r["units"], r["available_mw_published"]) == ("222", "22", 1, 0)
    p = one(rows, table_type="distribution_area", row_no="244")
    assert (p["name"], p["v1_kv"], p["units"], p["rated_mw"], p["available_mw_published"]) == \
        ("品川", "", 2, 0, 0)


def test_summary():
    rows, _ = rows_of(0)
    s = summarise(rows)
    assert len(s) == 1
    assert (s[0]["n_rows"], s[0]["n_zero"], s[0]["median_available_mw"]) == (4, 0, "12")
