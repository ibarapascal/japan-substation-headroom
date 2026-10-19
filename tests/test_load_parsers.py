"""Loading-file parsers, one test group per operator, on short excerpts of published files."""
import os

import numpy as np

from conftest import FIXTURES
from parse import operator_module
from parse.wide import parse_wide_rows
from pipeline.__main__ import column_key


def blocks(op, *names):
    m = operator_module(op)
    paths = [os.path.join(FIXTURES, n) for n in names]
    ctx = m.prepare(paths)
    out = []
    for p, n in zip(paths, names):
        out.extend(m.load_blocks(p, n, ctx))
    return out


def col(block, **kw):
    for i, c in enumerate(block.cols):
        if all(getattr(c, k) == v for k, v in kw.items()):
            return i, c
    raise AssertionError(f"no column {kw}")


def test_tohoku_apostrophes_bom_hour_ending():
    b, = blocks("tohoku", "tohoku_load_kikan.csv")
    assert b.time_convention == "hour_ending"
    assert str(b.ts[0]) == "2025-04-01T00:00:00"          # published 01:00 -> interval start
    i, c = col(b, sub_no="001")
    assert (c.name, c.v1, c.v2) == ("五戸変電所", "275", "154")
    assert b.values[0, i] == 128
    j, _ = col(b, sub_no="002", v1="500")
    assert np.isnan(b.values[0, j])                       # '-' -> missing
    assert {c.v2 for c in b.cols} >= {"154", "66", "6.6"}


def test_tohoku_unnamed_columns_and_trailing_blanks():
    b, = blocks("tohoku", "tohoku_load_local.csv")
    assert len(b.cols) == 7                               # trailing empty columns dropped
    i, c = col(b, sub_no="1307")
    assert c.name == "1307"
    assert column_key(c.name, c.sub_no, c.bank) == "#1307"
    k, c2 = col(b, sub_no="1104")
    assert column_key(c2.name, c2.sub_no, c2.bank) == "十三湖"


def test_tohoku_fy2020_preamble_cp932():
    b, = blocks("tohoku", "tohoku_load_fy2020.csv")
    assert str(b.ts[0]) == "2020-04-01T00:00:00"
    assert b.cols[0].name == "五戸変電所"


def test_hokkaido_bulk_and_local_transformers():
    bs = blocks("hokkaido", "hokkaido_load.zip")
    bulk = [b for b in bs if "kikan01" in b.source_file][0]
    local = [b for b in bs if "linetr" in b.source_file][0]
    assert bulk.source_file.startswith("hokkaido_load.zip!変圧器の潮流実績")  # CP932 member name
    assert bulk.cols[0].name == "西当別変電所" and bulk.cols[0].v1 == "275"
    assert all("変電所" in c.name or "発電所" in c.name for c in bulk.cols)
    # only interconnecting-transformer columns survive from the mixed line/transformer file
    assert len(local.cols) >= 1
    i, c = col(local, sub_no="4")
    assert (c.name, c.v1, c.v2) == ("幌延変電所", "100", "33")
    assert c.bank.startswith("4:")


def test_tepco_banks_aggregates_lines_and_marks():
    b, = blocks("tepco", "tepco_load_154kV.zip")
    assert b.cols[0].v1 == "154" and b.cols[0].v2 == ""
    elems = {(c.name, c.bank) for c in b.cols}
    # no line columns
    assert not any("L" in e or "線" in e for _n, e in elems)
    # 花畑: individual banks 1B,2B,3B,5B are published, so the sum column 1・2・3・5B is dropped
    assert ("花畑(変)", "1・2・3・5B") not in elems
    assert ("花畑(変)", "1B") in elems
    # 下総: only the sum column is published, so it is kept
    assert ("下総(変)", "1・2・3・4B") in elems
    assert b.marked is not None and b.marked.sum() > 0   # '*185' style values
    assert not np.isnan(b.values[-1][b.marked[-1]]).any()


def test_tepco_fy2018_timestamp_with_seconds():
    b, = blocks("tepco", "tepco_load_fy2018.zip")
    assert str(b.ts[0]) == "2018-04-01T00:00:00" and str(b.ts[1]) == "2018-04-01T01:00:00"
    assert b.values.dtype == np.float64


def test_tepco_66kv_group_distribution_banks():
    b, = blocks("tepco", "tepco_load_66kV.zip")
    i, c = col(b, name="お茶の水(変)", bank="1B")
    assert c.v1 == "66"
    assert column_key(c.name, c.sub_no, c.bank) == "お茶ノ水"


def test_chubu_new_and_old_layouts():
    bs = blocks("chubu", "chubu_load_new.xlsx", "chubu_load_old.xlsx")
    new = [b for b in bs if "new" in b.source_file and "154" in b.source_file][0]
    old = [b for b in bs if "old" in b.source_file and "154" in b.source_file][0]
    assert new.cols[0].name == "名北変電所" and new.cols[0].v2 == "77"
    assert str(new.ts[0]) == "2025-04-01T00:00:00"
    # old workbook: label in the fourth column, date + start time columns, names filled by No
    assert str(old.ts[0]) == "2018-04-01T00:00:00"
    i, c = col(old, sub_no="1013")
    assert (c.name, c.v1, c.v2) == ("名北変電所", "154", "77")
    assert old.values[0, i] == 125
    assert any("taken from other fiscal years" in n for n in old.notes)


def test_hokuriku_old_labels_and_name_voltage():
    b, = blocks("hokuriku", "hokuriku_load_fy2019.csv")
    i, c = col(b, sub_no="HSS001")
    assert c.v1 == "500" and column_key(c.name, c.sub_no, c.bank) == "中能登"
    b2, = blocks("hokuriku", "hokuriku_load_fy2023.csv")
    assert column_key(b2.cols[0].name, b2.cols[0].sub_no, b2.cols[0].bank) == "新寺田"


def test_kansai_note_row_and_fullwidth_ids():
    b, = blocks("kansai", "kansai_load_less.csv")
    assert b.cols[0].sub_no == "北A" and b.cols[0].name == "木代"
    m, = blocks("kansai", "kansai_load_more.csv")
    assert m.cols[0].sub_no == "A"                         # 'Ａ' normalised
    old, = blocks("kansai", "kansai_load_fy2018.csv")
    assert np.isnan(old.values).any()                      # empty cells -> missing


def test_chugoku_hour_ending():
    b, = blocks("chugoku", "chugoku_load.csv")
    assert b.time_convention == "hour_ending"
    assert str(b.ts[0]) == "2025-04-01T00:00:00"
    assert str(b.ts[-1]) == "2026-03-31T23:00:00"          # published 2026/4/1 0:00


def test_shikoku_dash_variants_and_preamble():
    b, = blocks("shikoku", "shikoku_load.csv")
    assert np.isnan(b.values[0, 0]) and b.values[0, 1] == 3
    old, = blocks("shikoku", "shikoku_load_fy2019.csv")
    assert old.cols[0].name == "川内変電所" and str(old.ts[0]) == "2019-04-01T00:00:00"


def test_shikoku_composite_secondary_voltage():
    rows = [["［単位：MW］"], ["変電所No.", "1", "2"], ["一次電圧(kV)", "187", "187"],
            ["二次電圧(kV)", "110,66", "66"], ["変電所名", "A変電所", "B変電所"],
            ["2024/4/1 0:00", "5", "－"]]
    b = parse_wide_rows(rows, "x")
    assert b.cols[0].v2 == "110/66" and np.isnan(b.values[0, 1])


def test_kyushu_csv_and_bulk_workbook():
    b, = blocks("kyushu", "kyushu_load.csv")
    assert b.cols[0].name == "大門" and b.cols[0].v2 == "22"
    x, = blocks("kyushu", "kyushu_load_bulk.xlsx")
    assert x.time_convention == "hour_ending"               # text 'YY/MM/DD HH' from 01
    # merged name cell: the second column of station 1 inherits No and name
    pair = [c for c in x.cols if c.sub_no == "1"]
    assert len(pair) == 2 and {c.v2 for c in pair} == {"220", "66"}
    assert all(c.name == "北九州" for c in pair)


def test_okinawa_csv_lines_skipped_and_workbooks():
    bs = blocks("okinawa", "okinawa_load_bulk.csv", "okinawa_load_local.csv",
                "okinawa_load_lines.csv", "okinawa_load_fy2020.xlsx",
                "okinawa_load_local_fy2022.xlsx")
    srcs = [b.source_file for b in bs]
    assert "okinawa_load_lines.csv" not in srcs            # transmission-line table skipped
    bulk = [b for b in bs if b.source_file == "okinawa_load_bulk.csv"][0]
    assert bulk.cols[0].v1 == "132" and bulk.cols[0].v2 == "66"
    local = [b for b in bs if b.source_file == "okinawa_load_local.csv"][0]
    assert column_key(local.cols[0].name, local.cols[0].sub_no, local.cols[0].bank) == "与根"
    assert any(c.v2 == "13.8" for c in local.cols)
    xl = [b for b in bs if b.source_file.startswith("okinawa_load_fy2020.xlsx")]
    assert len(xl) == 1 and xl[0].source_file.endswith("#変電所")
    assert xl[0].cols[0].name == "友寄変電所" and xl[0].cols[0].v2 == "66"   # filled from CSV
    assert str(xl[0].ts[1]) == "2020-04-01T01:00:00"


def test_table_shifted_right_with_leading_empty_column():
    import datetime as dt
    rows = [[None, "変電所No", 1031, 1034], [None, "一次電圧(kV)", 77, 77],
            [None, "二次電圧(kV)", 33, 33], [None, "変電所名", "稲永変電所", "六郷変電所"],
            [None, dt.datetime(2023, 4, 1, 0, 0), 5.04, 21.05],
            [None, dt.datetime(2023, 4, 1, 1, 0), 4.9, 17.6]]
    b = parse_wide_rows(rows, "x#77kV以下バンク")
    assert [c.sub_no for c in b.cols] == ["1031", "1034"]
    assert str(b.ts[1]) == "2023-04-01T01:00:00" and b.values[1, 1] == 17.6
