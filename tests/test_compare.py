"""Comparison of a rebuild with released tables (pipeline/compare.py)."""
import csv
import os

from pipeline.compare import cells_equal, compare_dirs, compare_table

FIELDS = ["operator", "fiscal_year", "substation_key", "v1_kv", "v2_kv", "peak_mw", "peak_ts_local"]
ROWS = [
    ["kansai", "2024", "A", "77", "6.6", "12.5", "2024-08-01 14:00:00"],
    ["kansai", "2024", "B", "77", "6.6", "30", "2024-07-30 15:00:00"],
    ["tepco", "2024", "C", "66", "", "101.25", "2025-01-10 10:00:00"],
]


def write(root, rel, rows, fields=FIELDS):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(fields)
        w.writerows(rows)
    return path


REL = "stats/substation_year_stats.csv"


def test_identical_and_within_tolerance(tmp_path):
    released, built = str(tmp_path / "rel"), str(tmp_path / "built")
    write(released, REL, ROWS)
    rows = [list(r) for r in reversed(ROWS)]          # row order does not matter
    rows[0][5] = "101.2500000000001"                  # within relative tolerance
    rows[1][5] = "30.0"                               # same number, other spelling
    write(built, REL, rows)
    assert compare_dirs(built, released, echo=lambda *_: None) == 0
    assert cells_equal("1.0000001", "1.0000002")
    assert not cells_equal("1.00001", "1.00002")
    assert not cells_equal("x", "y")


def test_value_difference_and_missing_extra_rows(tmp_path):
    released, built = str(tmp_path / "rel"), str(tmp_path / "built")
    p_rel = write(released, REL, ROWS)
    rows = [list(ROWS[0]), list(ROWS[2]), ["okinawa", "2024", "D", "66", "6.6", "1", ""]]
    rows[0][5] = "12.6"
    p_built = write(built, REL, rows)
    res = compare_table(p_built, p_rel, ("operator", "fiscal_year", "substation_key", "v1_kv", "v2_kv"))
    assert (res["missing_rows"], res["extra_rows"]) == (1, 1)
    assert (res["rows_differing"], res["cells_differing"]) == (1, 1)
    assert compare_dirs(built, released, echo=lambda *_: None) == 1


def test_partial_rebuild_and_strict(tmp_path):
    released, built = str(tmp_path / "rel"), str(tmp_path / "built")
    write(released, REL, ROWS)
    write(released, "sites/data_center_sites.csv", [["s1", "x"]], ["site_id", "site_name"])
    write(released, "manifest.csv", [["a"]], ["operator"])            # input index: not compared
    write(built, REL, ROWS)
    write(built, "stats/column_duplicates.csv", [["a"]], ["operator"])  # unreleased output
    lines = []
    assert compare_dirs(built, released, echo=lines.append) == 0
    assert any(l.startswith("[not in built] sites/") for l in lines)
    assert any(l.startswith("[not released] stats/column_duplicates") for l in lines)
    assert compare_dirs(built, released, strict=True, echo=lambda *_: None) == 1
