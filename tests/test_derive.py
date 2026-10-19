"""Station-year statistics and headroom reconstruction on synthetic series."""

import numpy as np

from derive.headroom import reconstruct
from derive.stats import Spill, aggregate_group


def ts_range(start, n):
    t0 = np.datetime64(start, "s")
    return t0 + np.arange(n) * np.timedelta64(3600, "s")


def add(sp, src, keys, v1, v2, banks, ts, values, op="x"):
    sp.add(op, src, keys, keys, v1, v2, banks, ts, np.asarray(values, dtype=float))


def run(sp):
    out = {}
    for op, fy, stems in sp.groups():
        out[(op, fy)] = aggregate_group(op, fy, stems)
    return out


def test_coincident_peak_and_strict_hours(tmp_path):
    sp = Spill(str(tmp_path))
    ts = ts_range("2024-04-01T00:00:00", 4)
    vals = np.array([[10, 5], [20, np.nan], [15, 15], [0, -1]])
    add(sp, "f1", ["A", "A"], ["66", "66"], ["6.6", "6.6"], ["1B", "2B"], ts, vals)
    banks, stations, dups = run(sp)[("x", 2024)]
    s, = stations
    assert s["n_banks"] == 2 and s["n_banks_reporting"] == 2
    assert s["valid_hours"] == 3                     # hour 1 has a missing bank
    assert s["peak_mw"] == 30 and s["peak_ts_local"] == "2024-04-01 02:00"
    assert s["negative_hours"] == 1 and s["bank_zero_hours"] == 1
    assert s["hours_in_year"] == 8760
    b1 = [b for b in banks if b["bank"] == "1B"][0]
    assert b1["max_mw"] == 20 and b1["missing_hours"] == 8760 - 4


def test_fiscal_year_split_and_half_year_files(tmp_path):
    sp = Spill(str(tmp_path))
    add(sp, "h1", ["A"], ["66"], ["22"], ["1"], ts_range("2025-03-31T22:00:00", 4), [[1], [2], [3], [4]])
    add(sp, "h2", ["A"], ["66"], ["22"], ["1"], ts_range("2025-10-01T00:00:00", 2), [[9], [8]])
    res = run(sp)
    assert set(res) == {("x", 2024), ("x", 2025)}
    _b, st, _d = res[("x", 2025)]
    assert st[0]["valid_hours"] == 4 and st[0]["peak_mw"] == 9 and st[0]["n_source_files"] == 2


def test_repeated_column_first_wins_and_conflicts(tmp_path):
    sp = Spill(str(tmp_path))
    ts = ts_range("2024-04-01T00:00:00", 3)
    add(sp, "a", ["A"], ["154"], [""], ["1B"], ts, [[1], [2], [np.nan]])
    add(sp, "b", ["A"], ["154"], [""], ["1B"], ts, [[1], [5], [7]])
    banks, st, dups = run(sp)[("x", 2024)]
    assert len(banks) == 1 and st[0]["peak_mw"] == 7
    d, = [d for d in dups if d["kind"] == "repeated_column"]
    assert d["overlap_hours"] == 2 and d["conflict_hours"] == 1


def test_same_values_under_other_voltage_label_dropped(tmp_path):
    sp = Spill(str(tmp_path))
    ts = ts_range("2024-04-01T00:00:00", 48)
    v = np.arange(1, 49, dtype=float).reshape(-1, 1)
    add(sp, "g154", ["A"], ["154"], [""], ["1B"], ts, v)
    add(sp, "gbulk", ["A"], [""], [""], ["1B"], ts, v)
    banks, st, dups = run(sp)[("x", 2024)]
    assert len(banks) == 1 and banks[0]["v1_kv"] == "154"
    assert any(d["kind"] == "same_values_other_voltage_label" for d in dups)


def test_groups_by_secondary_voltage(tmp_path):
    sp = Spill(str(tmp_path))
    ts = ts_range("2024-04-01T00:00:00", 2)
    add(sp, "f", ["A", "A", "A"], ["154", "77", "154"], ["66", "66", "22"], ["1", "2", "3"], ts,
        [[1, 2, 3], [1, 2, 3]])
    _b, st, _d = run(sp)[("x", 2024)]
    by = {s["v2_kv"]: s for s in st}
    assert by["66"]["peak_mw"] == 3 and by["66"]["v1_kv"] == "154;77"
    assert by["22"]["peak_mw"] == 3


def cap_row(op, key, v1, v2, units, rated, oper):
    return {"operator": op, "substation_key": key, "v1_kv": v1, "v2_kv": v2, "units": units,
            "rated_mw": rated, "operating_mw": oper, "category": "", "as_of": "2026-09"}


def st_row(op, key, v1, v2, peak, fy=2024):
    return {"operator": op, "fiscal_year": fy, "substation_key": key, "substation_raw": key,
            "v1_kv": v1, "v2_kv": v2, "peak_mw": peak, "peak_ts_local": "", "valid_hours": 10,
            "hours_in_year": 8760}


def test_headroom_definitions_and_join_statuses():
    caps = [cap_row("k", "A", "77", "6", 3, 60, 50), cap_row("k", "B", "77", "22", 1, 20, 20),
            cap_row("tepco", "C", "", "", 2, 40, 41), cap_row("tepco", "C", "154", "66", 2, 400, 300)]
    sts = [st_row("k", "A", "77", "6.6", 30), st_row("k", "B", "77", "22", 5),
           st_row("k", "B", "77", "33", 5), st_row("k", "Z", "77", "22", 5),
           st_row("tepco", "C", "66", "", 12), st_row("k", "#7", "", "", 1),
           st_row("c", "D", "154", "77", 1)]
    head, report = reconstruct(sts, caps, {"c"})
    h = {(r["operator"], r["substation_key"], r["v2_kv"]): r for r in head}
    a = h[("k", "A", "6.6")]
    assert a["join_status"] == "matched_key_v2"
    assert a["headroom_naive_mw"] == 20 and a["n1_capacity_mw"] == 40 and a["headroom_n1_mw"] == 10
    b = h[("k", "B", "22")]
    assert b["headroom_naive_mw"] == 15 and b["headroom_n1_mw"] is None and b["n1_note"] == "single_unit"
    assert h[("k", "B", "33")]["join_status"] == "unmatched_voltage"
    assert h[("k", "Z", "22")]["join_status"] == "unmatched_key"
    c = h[("tepco", "C", "")]
    assert c["join_status"] == "matched_key_v1" and c["operating_mw"] == 41   # blank-voltage row
    assert h[("k", "#7", "")]["join_status"] == "unnamed_column"
    assert h[("c", "D", "77")]["join_status"] == "no_capacity_table"
    rk = [r for r in report if r["operator"] == "k"][0]
    assert rk["matched"] == 2 and rk["named_load_groups"] == 4 and rk["match_rate_named"] == 0.5
