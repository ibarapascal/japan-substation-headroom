"""Capacity-table parsers."""
import os


from conftest import FIXTURES
from parse import operator_module
from parse.capacity import parse_capacity_rows, repair_split_thousands
from parse.common import csv_rows
from parse.tepco import split_first_column


def cap(op, name):
    return operator_module(op).capacity_rows(os.path.join(FIXTURES, name), name)


def by(rows, **kw):
    return [r for r in rows if all(r[k] == v for k, v in kw.items())]


def test_tohoku_footnote_dropped_and_dash_missing():
    rows = cap("tohoku", "tohoku_capacity.csv")
    assert all(r["v1_kv"] or r["v2_kv"] for r in rows)
    r = by(rows, substation_key="下北")[0]
    assert (r["units"], r["rated_mw"], r["operating_mw"], r["forecast_flow_mw"]) == (2, 190, 114, -149)
    assert r["available_mw_published"] is None
    assert r["as_of"] == "2026-09-03" or r["as_of"].startswith("2026-")


def test_hokkaido_zip_tr_member_and_spillover_cells():
    rows = cap("hokkaido", "hokkaido_capacity.zip")
    assert rows and all("_Tr_" in r["source_file"] for r in rows)
    r = by(rows, substation_key="幌延", v2_kv="6.6")[0]
    assert r["category"] == "distribution_6kV" and r["available_mw_published"] == 6


def test_tepco_layout_classes_and_quoted_thousands():
    rows = cap("tepco", "tepco_capacity.zip")
    toda = by(rows, substation_key="戸田")[0]
    assert (toda["v1_kv"], toda["v2_kv"], toda["publisher_class"]) == ("154", "66", "154kV")
    dist = [r for r in rows if r["publisher_class"] == "配電用変電所"]
    assert dist and all(r["v1_kv"] == "" and r["category"] == "voltage_unpublished" for r in dist)
    big = by(rows, substation_key="新福島", v2_kv="275")[0]
    assert big["rated_mw"] == 3000 and big["operating_mw"] == 2280   # "3,000" quoted
    assert big["publisher_class"] == "基幹 275kV"
    assert by(rows, substation_key="木挽町")                          # '木挽町(局配)'


def test_tepco_first_column():
    assert split_first_column("変東京都（23区） 配電用変電所 323") == ("東京都(23区)", "配電用変電所", "323")
    assert split_first_column("変基幹 275kV 1-1") == ("", "基幹 275kV", "1-1")


def test_shikoku_unquoted_thousands_split_and_footnotes():
    rows = cap("shikoku", "shikoku_capacity_kikan.csv")
    sendai = by(rows, substation_key="川内")[0]
    assert (sendai["units"], sendai["rated_mw"], sendai["operating_mw"]) == (2, 1425, 784)
    toyo = by(rows, substation_key="東予")[0]            # '1,713 ' here is units 1, rated 713
    assert (toyo["units"], toyo["rated_mw"], toyo["operating_mw"]) == (1, 713, 713)
    assert not any(r["substation_raw"].startswith("*") for r in rows)


def test_repair_negative_split_after_anchor():
    col = {"units": 4, "rated": 5, "operating": 6, "forecast": 8, "available": 9, "n1": 11}
    row = ["1", "X", "187", "66", "2", "570", "313", "熱容量", "-1", "345 ", "－", "－", "可"]
    fixed = repair_split_thousands(row, col)
    assert fixed[8] == "-1345" and fixed[11] == "可"


def test_hokuriku_blank_names_kept_unjoinable():
    rows = cap("hokuriku", "hokuriku_capacity.csv")
    blank = [r for r in rows if not r["substation_raw"]]
    assert all(r["substation_key"].startswith("#") for r in blank)


def test_kansai_quoted_csv():
    rows = cap("kansai", "kansai_capacity.csv")
    assert by(rows, substation_key="松ケ丘")              # 松が丘 folded
    assert rows[0]["as_of"] == "2026-07-07" or rows[0]["as_of"].startswith("20")


def test_chugoku_multiline_cell_and_tr_members_only():
    rows = cap("chugoku", "chugoku_capacity.zip")
    assert rows and all("_tr_" in r["source_file"] for r in rows)
    text = ("2026年9月28日更新,,,,,,,,,,,,\n"
            "変電所 No,変電所名,電圧(一次)（kV）,電圧(二次)（kV）,台数,設備容量(100%×台数)（MW）,"
            "運用容量値（MW）,運用容量制約要因,予想潮流,空容量(当該設備)（MW）,空容量(上位系等考慮)（MW）,"
            "N-1電制適用可否,備考\n"
            "S1,A変電所,66,6,2,38,33,熱容量,―,7,0,\"不可\n♯３\",\"a\nb\"\n"
            "S2,B変電所,66,22,1,9,6,熱容量,―,6,0,可,\n").encode("cp932")
    recs = parse_capacity_rows(csv_rows(text)[0], "chugoku", "x.csv")
    assert [r["substation_key"] for r in recs] == ["A", "B"]
    assert recs[0]["v2_kv"] == "6" and recs[0]["category"] == "distribution_6kV"


def test_kyushu_and_okinawa():
    k = cap("kyushu", "kyushu_capacity.zip")
    assert k and k[0]["rated_mw"] == 15                     # '15 ' trailing space
    o = cap("okinawa", "okinawa_capacity.csv")
    assert o[0]["substation_key"] == "与根" and o[0]["v2_kv"] == "22"
