"""Cell, voltage, timestamp and encoding helpers."""
import datetime as dt
import zipfile

import pytest

from parse.common import (decode_text, kv_join_key, norm_kv, parse_hour, parse_number,
                          parse_ts, zip_member_name, fy_hours)


@pytest.mark.parametrize("tok", ["-", "ー", "－", "―", "‐", "欠測", "＊", "*", "", "  ", None])
def test_missing_tokens(tok):
    assert parse_number(tok) is None


@pytest.mark.parametrize("s,v", [("1,800", 1800.0), ("１２", 12.0), ("'128", 128.0),
                                 ("-5", -5.0), ("−5", -5.0), (" 15 ", 15.0), (3, 3.0)])
def test_numbers(s, v):
    assert parse_number(s) == v


@pytest.mark.parametrize("s,kv", [("132kV", "132"), ("6.6", "6.6"), (66.0, "66"),
                                  ("110,66", "110/66"), ("22-13.8", "22-13.8"),
                                  ("'275", "275"), ("－", ""), ("100kV", "100")])
def test_norm_kv(s, kv):
    assert norm_kv(s) == kv


def test_kv_join_key():
    assert kv_join_key("6") == kv_join_key("6.6") == kv_join_key("6.9") == "6.6"
    assert kv_join_key("22") == "22"


@pytest.mark.parametrize("s,t", [
    ("2024/4/1 0:00", dt.datetime(2024, 4, 1, 0)),
    ("2025-04-01 00:00:00", dt.datetime(2025, 4, 1, 0)),
    ("2024年04月01日 00時", dt.datetime(2024, 4, 1, 0)),
    ("2018年04月01日 13時00分00秒", dt.datetime(2018, 4, 1, 13)),
    ("23/04/01 01", dt.datetime(2023, 4, 1, 1)),
    ("2024/4/1 24:00", dt.datetime(2024, 4, 2, 0)),
    ("'2025/4/1 1:00", dt.datetime(2025, 4, 1, 1)),
    ("［単位：MW］", None),
    ("変電所No.", None),
])
def test_parse_ts(s, t):
    assert parse_ts(s) == t


def test_parse_hour():
    assert parse_hour("01:00:00") == 1
    assert parse_hour(dt.time(5, 0)) == 5
    assert parse_hour("13時") == 13


def test_decode_utf8_bom_and_cp932():
    assert decode_text("変電所".encode("utf-8-sig"))[0] == "変電所"
    assert decode_text("変電所".encode("cp932")) == ("変電所", "cp932")


def test_zip_member_name_cp932():
    info = zipfile.ZipInfo("x")
    info.filename = "潮流実績_66kV/jisseki.csv".encode("cp932").decode("cp437")
    info.flag_bits = 0
    assert zip_member_name(info) == "潮流実績_66kV/jisseki.csv"
    info2 = zipfile.ZipInfo("潮流.csv")
    info2.flag_bits = 0x800
    assert zip_member_name(info2) == "潮流.csv"


def test_fiscal_year_hours():
    assert fy_hours(2023) == 8784  # includes 2024-02-29
    assert fy_hours(2024) == 8760
