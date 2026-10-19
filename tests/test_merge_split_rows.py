from parse.capacity import merge_split_rows


def rec(**kw):
    base = {"operator": "x", "source_file": "f", "substation_key": "A", "v1_kv": "66", "v2_kv": "22", "units": 1,
            "rated_mw": 9.0, "operating_mw": 9.0, "forecast_flow_mw": None, "available_mw_published": None}
    base.update(kw)
    return base


def test_split_lines_are_merged():
    rows, n = merge_split_rows([rec(forecast_flow_mw=-11.0), rec(available_mw_published=0.0), rec(substation_key="B")])
    assert n == 1 and len(rows) == 2
    assert rows[0]["forecast_flow_mw"] == -11.0 and rows[0]["available_mw_published"] == 0.0


def test_different_specs_are_kept():
    rows, n = merge_split_rows([rec(), rec(units=2, rated_mw=18.0)])
    assert n == 0 and len(rows) == 2
