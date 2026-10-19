"""Data center site register: classification, merging, register assembly on a small excerpt."""
import os

from conftest import FIXTURES
from derive.dc_sites import (SITES_DIR, build_register, classify, classify_type, merge_variants,
                             read_table, split_address)


def test_classify_rules():
    assert classify("アマゾンデータサービスジャパン株式会社 関東東第1センター", "x")[0] == "confirmed"
    assert classify("株式会社ABC 第2データセンター", "情報サービス業") == ("confirmed", ["name_keyword"])
    assert classify("株式会社ABC 関東DC", "倉庫業")[0] == "excluded"
    assert classify("株式会社ABC 中央病院", "医療業")[0] == "excluded"
    assert classify("富士通株式会社 富士通株式会社　横浜システムセンター", "情報サービス業")[0] == "suspected"
    assert classify("株式会社ABC 情報センター", "通信業")[0] == "suspected"
    assert classify("株式会社ABC 情報センター", "鉄鋼業")[0] == "excluded"


def test_type_rules_and_address():
    assert classify_type("エクイニクス・ハイパースケール１・ジャパン特定目的会社 X") == \
        ("hyperscale_cloud", "operator_rule")
    assert classify_type("エクイニクス・ジャパン株式会社 X")[0] == "colo_metro"
    assert classify_type("株式会社ABC 第2データセンター") == ("telecom_enterprise", "default")
    assert split_address("東京都多摩市") == ("東京都", "多摩市")
    assert split_address("京都府相楽郡精華町") == ("京都府", "相楽郡精華町")
    assert split_address("神奈川県横浜市") == ("神奈川県", "横浜市")


def test_merge_name_variants():
    base = {"code": "1", "industry": "通信業", "addr": "東京都江東区", "page": "", "office": "",
            "co2_2021": "", "co2_2022": "", "co2_2023": ""}
    rows = [dict(base, name="株式会社ABC 東京第一センター", status="suspected", reasons="a",
                 co2_2021="10"),
            dict(base, name="株式会社ABC 東京第一センター（別館含む）", status="confirmed",
                 reasons="b", co2_2023="12"),
            dict(base, name="株式会社ABC 大阪センター", status="suspected", reasons="a")]
    m = merge_variants(rows)
    assert len(m) == 2
    t = [r for r in m if "東京" in r["name"]][0]
    assert (t["status"], t["co2_2021"], t["co2_2023"]) == ("confirmed", "10", "12")
    assert t["name"].endswith("（別館含む）")


def test_curated_tables_are_well_formed():
    cur = read_table("curated_sites.csv")
    assert len(cur) == len({r["site_name"] for r in cur})
    assert all(r["status"] in ("confirmed", "suspected") for r in cur)
    assert all(r["type"] in ("hyperscale_cloud", "colo_metro", "telecom_enterprise", "ai_campus")
               for r in cur)
    assert all(r["coord_precision"] in ("municipality", "district", "address") for r in cur)
    assert all(r["source_ref"] for r in cur)
    for r in cur:
        if r["capacity_mw"]:
            float(r["capacity_mw"])


def test_register_from_excerpt():
    rows, stats = build_register(os.path.join(FIXTURES, "eegs_sample"), SITES_DIR, years=[2023])
    eegs = [r for r in rows if r["eegs_emitter_code"]]
    assert stats["eegs"] == len(eegs) == 5  # hospital and distribution center excluded
    by = {r["site_name"]: r for r in eegs}
    aws = by["関東東第1センター"]
    assert (aws["operator"], aws["prefecture"], aws["municipality"], aws["type"], aws["status"],
            aws["identification_basis"], aws["eegs_co2_t_fy2023"], aws["coord_precision"]) == \
        ("アマゾンデータサービスジャパン株式会社", "千葉県", "印西市", "hyperscale_cloud", "confirmed",
         "eegs_operator_list", "113316", "municipality")
    ty = [r for k, r in by.items() if "TY12x" in k][0]
    assert (ty["capacity_mw"], ty["operator_group"], ty["type_basis"]) == \
        ("54", "Equinix (xScale)", "operator_fact")
    fj = [r for k, r in by.items() if "館林" in k][0]
    assert (fj["status"], fj["identification_basis"]) == ("confirmed", "eegs+operator_disclosure")
    tama = by["多摩TC(多摩4NC)"]
    assert (tama["status"], tama["identification_basis"]) == ("confirmed", "eegs+operator_disclosure")
    assert "biz.kddi.com" in tama["source_ref"]
    kd = [r for k, r in by.items() if "豊洲" in k][0]
    assert (kd["status"], kd["identification_basis"]) == ("suspected", "eegs_ambiguous_name")
    assert len({r["site_id"] for r in rows}) == len(rows)
    assert stats["curated"] == len(read_table("curated_sites.csv"))
