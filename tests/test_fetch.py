"""Link selection, archived-copy URLs and manifest handling (no network access)."""
import os

from fetch import archive, manifest
from fetch.sources import select_targets

PAGE = """
<h3>2024年度</h3>
<a href="/var/rev0/1/8787/jisseki_kikan00_tr_2024_09.csv">潮流実績（変圧器）（2,822KB）</a>
<a href="/var/rev0/1/8786/jisseki_kikan00_line_2024_09.csv">潮流実績（送電線）（3,306KB）</a>
<a href="/var/rev0/0925/6795/td_oLsu7j3Y.zip">変圧器CSV（zipファイル）（33KB）</a>
<a href="/var/rev0/0925/6794/td_vHd7yu8i.zip">送電線CSV（zipファイル）（41KB）</a>
<a href="/var/rev0/0925/8793/td_t2PJhcyF.xlsx">潮流実績（変圧器）（4,130KB）</a>
"""


def test_kyushu_random_names_from_link_text():
    ts = select_targets("kyushu", "https://www.kyuden.co.jp/td/x.html", PAGE)
    got = {(t.kind, os.path.basename(t.local_name)) for t in ts}
    assert got == {("load_tr", "jisseki_kikan00_tr_2024_09.csv"), ("load_tr", "td_t2PJhcyF.xlsx"),
                   ("capacity_tr", "td_oLsu7j3Y.zip")}


def test_image_map_links_and_relative_paths():
    page = ('<map><area shape="rect" href="./data/sys_capa_local01_tr_202609_02.csv" alt="CSV">'
            '<area shape="rect" href="./pdf/sys_capa_local01_tr_202609_02.pdf" alt="PDF"></map>')
    ts = select_targets("tohoku", "https://nw.tohoku-epco.co.jp/consignment/system/announcement/", page)
    assert [t.url for t in ts] == [
        "https://nw.tohoku-epco.co.jp/consignment/system/announcement/data/sys_capa_local01_tr_202609_02.csv"]


def test_tepco_query_string_and_snapshot_pdf_ignored():
    page = ('<a href="/pg/consignment/system/pdf/tyouryu_66kV.zip?251028">2024年度_潮流実績</a>'
            '<a href="/pg/consignment/system/pdf/jisseki_kikan.pdf?251028">実績系統図</a>'
            '<a href="/pg/consignment/system/pdf/csv_yosochoryu_tokyo.zip">CSV</a>')
    ts = select_targets("tepco", "https://www.tepco.co.jp/pg/consignment/system/", page)
    assert [t.local_name for t in ts] == ["tepco/load_tr/tyouryu_66kV.zip",
                                          "tepco/capacity_tr/csv_yosochoryu_tokyo.zip"]


def test_hokkaido_uses_zip_not_map_pdf():
    page = ('<a href="zip/sys_capa_local01.zip">予想潮流等一覧表</a>'
            '<a href="pdf/map_forecast_tide_list_01.pdf">マップ</a>')
    ts = select_targets("hokkaido", "https://www.hepco.co.jp/network/a/b.html", page)
    assert [t.kind for t in ts] == ["capacity_tr"]


def test_wayback_urls():
    assert archive.wayback_url("tyouryuuzisseki2020_20220420.zip").endswith(
        "/web/20220420084550/https://www.tepco.co.jp/pg/consignment/system/pdf/tyouryuuzisseki2020.zip")
    assert archive.wayback_url("unknown.zip") == "archived_copy"


def test_manifest_roundtrip(tmp_path):
    p = str(tmp_path / "manifest.csv")
    rows = manifest.load(p)
    manifest.upsert(rows, {"operator": "x", "kind": "load_tr", "url": "u", "local_name": "x/a.csv",
                           "bytes": 3, "sha256": "ab", "retrieved_at_utc": "t", "http_status": 200})
    manifest.upsert(rows, {"operator": "c", "kind": "capacity_tr", "url": "m", "local_name": "",
                           "http_status": "not_published_as_file"})
    manifest.save(p, rows)
    again = manifest.load(p)
    assert again["x/a.csv"]["sha256"] == "ab" and len(again) == 2


def test_archive_download_uses_raw_captures(tmp_path, monkeypatch):
    calls = []

    def fake_download(url, dest, min_interval=0):
        calls.append((url, dest, min_interval))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f:
            f.write(b"zip")
        return 200, 3, "x"

    monkeypatch.setattr(archive, "download_to", fake_download)
    assert archive.download(str(tmp_path), interval=7.0) == 0
    assert len(calls) == len(archive.WAYBACK)
    assert all("id_/https://www.tepco.co.jp/" in u and iv == 7.0 for u, _d, iv in calls)
    rows = manifest.load(str(tmp_path / "manifest.csv"))
    assert {r["local_name"] for r in rows.values()} == {
        f"tepco_history/wayback/{n}" for n in archive.WAYBACK}
    assert all(r["url"].startswith("https://web.archive.org/web/") for r in rows.values())
    calls.clear()
    assert archive.download(str(tmp_path)) == 0 and calls == []   # already present: skipped
