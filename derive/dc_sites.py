"""Data center site register from facility-level GHG reports and public announcements.

Two sources are combined:

1. EEGS facility-level emission files (温室効果ガス排出量算定・報告・公表制度, Ministry of the
   Environment), FY2021-FY2023, national download (one zip per fiscal year). Every facility is
   classified from its published name and industry:
     excluded   name matches a non-data-center facility type (hospital, power plant, transmitter
                station, R&D, head office, sales office, factory, substation, ...), or the name
                contains "DC" while the industry is wholesale / retail / road freight / food /
                warehousing (distribution center);
     confirmed  the reporting company is on the list of data-center operators (OPERATORS_DC), or
                the facility name contains a data-center keyword (データセンター, IDC, テレハウス,
                コロケーション, ...);
     suspected  a company with mixed businesses (OPERATORS_MIXED) and an ambiguous facility name
                (システムセンター, ネットワークセンター, 情報センター, TC/NC, ...), or an ambiguous
                name in a data-center-adjacent industry (internet services, telecommunications,
                information services, broadcasting, media production);
     anything else is excluded.
   Rows are keyed by reporting company code and facility (the `office` parameter of the EEGS
   facility page); a facility keeps the highest status seen in any year and its latest name,
   industry and municipality. Facilities of one company whose normalised names are equal or
   contained in one another are merged. Suspected facilities identified as data centers by the
   operator's own disclosure are raised to confirmed (sites/eegs_overrides.csv).
2. Public announcements (operator releases, municipal and ministry documents, news) for sites
   that do not appear in EEGS (below the reporting threshold, new or planned):
   sites/curated_sites.csv. Disclosed capacities and timelines of EEGS sites:
   sites/eegs_site_facts.csv.

Site type (hyperscale_cloud, colo_metro, telecom_enterprise, ai_campus) is assigned from the
company name (TYPE_RULES), overridden per reporting company by sites/eegs_operator_facts.csv;
facilities matching no rule default to telecom_enterprise.
"""
from __future__ import annotations

import csv
import hashlib
import io
import os
import re
import unicodedata
import zipfile
from typing import Dict, Iterable, Iterator, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

SITES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sites")
EEGS_SEARCH = "https://eegs.env.go.jp/ghg-santeikohyo-result/search"
YEARS = [2021, 2022, 2023]

SITE_FIELDS = [
    "site_id", "site_name", "operator", "operator_group", "prefecture", "municipality", "type",
    "type_basis", "status", "identification_basis", "capacity_mw", "capacity_basis",
    "capacity_note", "timeline", "eegs_emitter_code", "eegs_industry", "eegs_co2_t_fy2021",
    "eegs_co2_t_fy2022", "eegs_co2_t_fy2023", "lat", "lon", "coord_precision",
    "possible_duplicate_of", "source_type", "source_ref",
]


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


# ---- classification rules --------------------------------------------------------------------

DC_NAME_RE = re.compile(
    r"データセンター|データーセンター|データセンタ|クラウドセンタ|コロケーション|"
    r"(?<![ぁ-んァ-ヶー一-龠A-Za-z])i?DC(?:ビル|センター|フロンティア|$|[^A-Za-z])|"
    r"テレハウス|Telehouse"
)
LOGISTICS_INDUSTRIES = {
    "飲食料品卸売業", "織物・衣服・身の回り品小売業", "道路貨物運送業", "各種商品小売業",
    "その他の卸売業", "食料品製造業", "倉庫業", "農畜産物・水産物卸売業", "機械器具卸売業",
}
AMBIGUOUS_NAME_RE = re.compile(
    r"システムセンター|情報センター|システムラボラトリ|コンピュータセンター|"
    r"ネットワークセンター|情報システムセンター|システムプラザ|システム棟|"
    r"(?<![ぁ-んァ-ヶー一-龠A-Za-z])[TN]C(?:[^A-Za-z]|$)|(?<![ぁ-んァ-ヶー一-龠A-Za-z])NC(?:[^A-Za-z]|$)|"
    r"演算センター|技術センター|イノベーションセンター"
)
HARD_EXCLUDE_RE = re.compile(
    r"病院|発電所|送信所|通信所|衛星通信|研究開発|Ｒ＆Ｄ|R&D|本社事務所|評価室|"
    r"本社(?:ビル)?$|本社（|オフィス$|オフィス（|オフィス\(|"
    r"^本社|支社|営業所|工場$|機器室|送電|変電"
)
OPERATORS_DC = [
    "アマゾンデータサービスジャパン", "グーグル・クラウド・ジャパン合同会社", "ＡＳＡ合同会社",
    "ASA合同会社", "Coltデータセンターサービス", "Ｃｏｌｔデータセンターサービス",
    "Inzai Development", "Ｉｎｚａｉ Ｄｅｖｅｌｏｐｍｅｎｔ", "エクイニクス", "Equinix",
    "デジタル東京", "デジタル大阪", "デジタル埼玉", "デジタル福岡", "AirTrunk", "エアトランク",
    "エスティーティー", "さくらインターネット", "ＩＤＣフロンティア", "IDCフロンティア",
    "インターネットイニシアティブ", "デジタルリアルティ", "Digital Realty", "Global Data Centers",
    "グローバルデータセンターズ", "丸の内ダイレクトアクセス", "日本ＧＬＰ", "日本GLP",
    "三菱総研ＤＣＳ", "三菱総研DCS", "株式会社ＱＴｎｅｔ", "株式会社QTnet", "株式会社ＳＴＮｅｔ",
    "株式会社STNet", "ＦＲＴ株式会社", "信組情報サービス",
]
OPERATORS_MIXED = [
    "富士通株式会社", "日本電気株式会社", "株式会社日立製作所", "株式会社日立システムズ",
    "エヌ・ティ・ティ・コムウェア", "日本アイ・ビー・エム", "キンドリルジャパン",
    "株式会社野村総合研究所", "ＴＩＳ株式会社", "TIS株式会社", "株式会社アイネット",
    "日鉄ソリューションズ", "三菱電機インフォメーションネットワーク",
    "パナソニックインフォメーションシステムズ", "株式会社シーイーシー", "株式会社インテック",
    "ＳＣＳＫ株式会社", "SCSK株式会社", "みずほリサーチ＆テクノロジーズ", "鉄道情報システム",
    "一般社団法人しんきん共同センター", "株式会社しんきん情報システムセンター",
    "株式会社日本総合研究所", "ＫＤＤＩ株式会社", "KDDI株式会社", "ソフトバンク株式会社",
    "エヌ・ティ・ティコミュニケーションズ", "エヌ・ティ・ティ・コミュニケーションズ",
    "エヌ・ティ・ティ・データ", "株式会社ＮＴＴデータグループ", "キヤノンＩＴソリューションズ",
    "日本電子計算株式会社", "セコムトラストシステムズ", "沖電気工業", "エムアンドシーシステム",
    "オージス総研", "ＬＩＮＥヤフー", "LINEヤフー", "ヤフー株式会社",
]
DC_ADJACENT_INDUSTRIES = {
    "インターネット附随サービス業", "通信業", "情報サービス業", "放送業",
    "映像・音声・文字情報制作業",
}
TYPE_RULES = [
    (["アマゾンデータサービスジャパン", "ASA合同会社", "グーグル・クラウド・ジャパン", "AirTrunk",
      "デジタル大阪１", "デジタル大阪1"], "hyperscale_cloud"),
    (["エクイニクス・ハイパースケール"], "hyperscale_cloud"),
    (["エクイニクス", "Ｃｏｌｔ", "Coltデータセンター", "デジタル東京", "デジタル大阪", "デジタル埼玉",
      "デジタル福岡", "さくらインターネット", "ＩＤＣフロンティア", "IDCフロンティア",
      "インターネットイニシアティブ", "三菱総研ＤＣＳ", "野村総合研究所", "野村證券",
      "シティグループ", "信組情報サービス", "丸の内ダイレクトアクセス", "ＳＣＳＫ", "SCSK"],
     "colo_metro"),
    (["エヌ・ティ・ティコミュニケーションズ", "エヌ・ティ・ティ・コミュニケーションズ", "ＫＤＤＩ",
      "KDDI", "ソフトバンク", "富士通", "日本電気", "日立製作所", "TIS", "ＴＩＳ", "日鉄ソリューションズ",
      "三菱電機インフォメーションネットワーク", "アイネット", "インテック", "シーイーシー",
      "日本電子計算", "ＱＴｎｅｔ", "QTnet", "ＳＴＮｅｔ", "STNet", "TOKAIコミュニケーションズ",
      "パワー・アンド・ＩＴ", "両備システムズ", "ＦＲＴ", "FRT", "オプテージ", "エヌ・ティ・ティ・データ",
      "ＮＴＴデータ", "キンドリルジャパン"], "telecom_enterprise"),
]
DEFAULT_TYPE = "telecom_enterprise"


def classify(name: str, industry: str) -> Tuple[str, List[str]]:
    """(status, reasons) of one EEGS facility from its published name and industry."""
    n = nfkc(name)
    if HARD_EXCLUDE_RE.search(n):
        return "excluded", ["non_dc_facility_type"]
    kw = bool(DC_NAME_RE.search(n))
    if kw and industry in LOGISTICS_INDUSTRIES:
        return "excluded", ["distribution_center"]
    if any(nfkc(op) in n for op in OPERATORS_DC):
        return "confirmed", ["operator_list"]
    if kw:
        return "confirmed", ["name_keyword"]
    ambiguous = bool(AMBIGUOUS_NAME_RE.search(n))
    if ambiguous and any(nfkc(op) in n for op in OPERATORS_MIXED):
        return "suspected", ["mixed_operator", "ambiguous_name"]
    if ambiguous and industry in DC_ADJACENT_INDUSTRIES:
        return "suspected", ["ambiguous_name", "adjacent_industry"]
    return "excluded", ["no_match"]


def classify_type(name: str) -> Tuple[str, str]:
    n = nfkc(name)
    for keys, t in TYPE_RULES:
        if any(nfkc(k) in n for k in keys):
            return t, "operator_rule"
    return DEFAULT_TYPE, "default"


# ---- EEGS input ------------------------------------------------------------------------------

def iter_eegs_rows(eegs_dir: str, year: int) -> Iterator[List[str]]:
    """Rows of one fiscal year: national_office_<FY>.zip, or an extracted search_result_<FY>.csv."""
    zpath = os.path.join(eegs_dir, f"national_office_{year}.zip")
    if os.path.exists(zpath):
        with zipfile.ZipFile(zpath) as z:
            member = next(n for n in z.namelist() if n.endswith(".csv"))
            with z.open(member) as fb:
                r = csv.reader(io.TextIOWrapper(fb, encoding="utf-8-sig", newline=""))
                next(r)
                for row in r:
                    yield row
        return
    for root, _d, files in os.walk(eegs_dir):
        for fn in files:
            if fn == f"search_result_{year}.csv":
                with open(os.path.join(root, fn), newline="", encoding="utf-8-sig") as f:
                    r = csv.reader(f)
                    next(r)
                    yield from r
                return
    raise FileNotFoundError(f"EEGS FY{year}: national_office_{year}.zip not found in {eegs_dir}")


def office_of(url: str) -> str:
    return parse_qs(urlparse(url).query).get("office", [""])[0]


def collect(eegs_dir: str, years: Iterable[int] = YEARS) -> List[Dict[str, str]]:
    """Candidate facilities over all years, one per (company code, facility)."""
    rows: Dict[Tuple[str, str], Dict[str, str]] = {}
    for year in years:
        for rec in iter_eegs_rows(eegs_dir, year):
            corp_num, code, name, _kind, industry, addr, co2, page = rec[:8]
            status, reasons = classify(name, industry)
            if status == "excluded":
                continue
            key = (code, nfkc(office_of(page)))
            if key not in rows:
                rows[key] = {"code": code, "status": status, "reasons": ";".join(reasons),
                             "co2_2021": "", "co2_2022": "", "co2_2023": ""}
            r = rows[key]
            r[f"co2_{year}"] = co2
            r.update({"name": name, "industry": industry, "addr": addr, "page": page,
                      "office": office_of(page)})
            if status == "confirmed":
                r["status"] = "confirmed"
                r["reasons"] = ";".join(reasons)
    out = list(rows.values())
    out.sort(key=lambda x: -int(x["co2_2023"] or x["co2_2022"] or x["co2_2021"] or 0))
    return out


def _merge_key(name: str) -> str:
    s = re.sub(r"\s+", "", nfkc(name))
    s = re.sub(r"（.*?）|\(.*?\)", "", s)
    for w in ("株式会社", "合同会社", "特定目的会社", "一般社団法人"):
        s = s.replace(w, "")
    return s


def merge_variants(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Merge facilities of one company whose normalised names are equal or nested (spelling
    variants of the same facility across fiscal years)."""
    groups: Dict[str, List[Dict[str, str]]] = {}
    for r in rows:
        groups.setdefault(r["code"], []).append(r)
    merged = []
    for code, grp in groups.items():
        keys = [(_merge_key(r["name"]), r) for r in grp]
        used = [False] * len(keys)
        for i, (ki, ri) in enumerate(keys):
            if used[i]:
                continue
            cluster = [ri]
            used[i] = True
            for j in range(i + 1, len(keys)):
                kj, rj = keys[j]
                if not used[j] and (ki == kj or ki in kj or kj in ki):
                    cluster.append(rj)
                    used[j] = True
            best = max(cluster, key=lambda c: len(c["name"]))
            last = cluster[-1]
            out = {"code": code, "name": best["name"], "office": best["office"],
                   "page": best["page"], "industry": last["industry"], "addr": last["addr"],
                   "status": "confirmed" if any(c["status"] == "confirmed" for c in cluster)
                   else "suspected",
                   "reasons": ";".join(sorted(set(sum((c["reasons"].split(";")
                                                       for c in cluster), []))))}
            for y in YEARS:
                vals = [c[f"co2_{y}"] for c in cluster if c[f"co2_{y}"]]
                out[f"co2_{y}"] = vals[-1] if vals else ""
            merged.append(out)
    merged.sort(key=lambda x: -int(x["co2_2023"] or x["co2_2022"] or x["co2_2021"] or 0))
    return merged


# ---- curated inputs --------------------------------------------------------------------------

def read_table(name: str, sites_dir: str = SITES_DIR) -> List[Dict[str, str]]:
    with open(os.path.join(sites_dir, name), newline="", encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if not (r.get(next(iter(r))) or "").startswith("#")]


def apply_overrides(rows: List[Dict[str, str]], overrides: List[Dict[str, str]]) -> None:
    for r in rows:
        for o in overrides:
            if o["name_contains"] in r["name"]:
                r["status"] = "confirmed"
                r["reasons"] += ";" + o["basis"]
                r["override_ref"] = o["source_ref"]
                break


PREF_RE = re.compile(r"^(東京都|北海道|(?:京都|大阪)府|.{2,3}県)(.*)$")


def split_address(addr: str) -> Tuple[str, str]:
    m = PREF_RE.match(addr)
    return (m.group(1), m.group(2)) if m else (addr, "")


def site_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha1("|".join(nfkc(p) for p in parts).encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{h}"


def identification_basis(reasons: str) -> str:
    rs = set(reasons.split(";"))
    if "operator_disclosure" in rs:
        return "eegs+operator_disclosure"
    if "brand_pattern" in rs:
        return "eegs+brand_pattern"
    if "operator_list" in rs:
        return "eegs_operator_list"
    if "name_keyword" in rs:
        return "eegs_name_keyword"
    return "eegs_ambiguous_name"


def _office_name(name: str, office: str) -> Tuple[str, str]:
    """(operator, facility) from the EEGS 'company facility' name and the facility parameter."""
    n = nfkc(name).strip()
    o = nfkc(office).strip()
    if o and n.endswith(o) and len(n) > len(o):
        return n[: len(n) - len(o)].strip(), o
    if " " in n:
        a, b = n.split(" ", 1)
        return a, b
    return n, n


def _dup_key(municipality: str, facility: str) -> str:
    s = re.sub(r"\s+", "", nfkc(facility))
    s = re.sub(r"^(?:エヌ・ティ・ティ・?コミュニケーションズ|NTTコム|ＮＴＴコム)", "", s)
    s = re.sub(r"(?:株式会社|合同会社|特定目的会社)", "", s)
    s = s.replace("LINEヤフー", "").replace("ヤフー", "").replace("KDDI", "")
    return municipality + "|" + s.upper()


def build_register(eegs_dir: str, sites_dir: str = SITES_DIR,
                   years: Iterable[int] = YEARS) -> Tuple[List[Dict[str, object]], Dict[str, int]]:
    cand = merge_variants(collect(eegs_dir, years))
    apply_overrides(cand, read_table("eegs_overrides.csv", sites_dir))
    op_facts = {r["eegs_emitter_code"]: r for r in read_table("eegs_operator_facts.csv", sites_dir)}
    site_facts = read_table("eegs_site_facts.csv", sites_dir)
    points = {(r["prefecture"], r["municipality"]): r
              for r in read_table("municipality_points.csv", sites_dir)}
    out: List[Dict[str, object]] = []
    for r in cand:
        pref, muni = split_address(r["addr"])
        operator, facility = _office_name(r["name"], r["office"])
        t, tb = classify_type(r["name"])
        of = op_facts.get(r["code"])
        if of and of.get("type"):
            t, tb = of["type"], "operator_fact"
        fact = next((f for f in site_facts if f["eegs_emitter_code"] == r["code"]
                     and f["name_contains"] in nfkc(r["name"])), None)
        pt = points.get((pref, muni), {})
        refs = [r["page"] or EEGS_SEARCH]
        types = ["eegs"]
        if r.get("override_ref"):
            refs.append(r["override_ref"])
            types.append("operator_disclosure")
        if fact:
            refs += [x for x in fact["source_ref"].split(";") if x]
            types += [x for x in fact["source_type"].split(";") if x and x not in types]
        out.append({
            "site_id": site_id("eegs", r["code"], facility), "site_name": facility,
            "operator": operator, "operator_group": (of or {}).get("operator_group", ""),
            "prefecture": pref, "municipality": muni, "type": t, "type_basis": tb,
            "status": r["status"], "identification_basis": identification_basis(r["reasons"]),
            "capacity_mw": (fact or {}).get("capacity_mw", ""),
            "capacity_basis": (fact or {}).get("capacity_basis", ""),
            "capacity_note": (fact or {}).get("capacity_note", ""),
            "timeline": (fact or {}).get("timeline", ""),
            "eegs_emitter_code": r["code"], "eegs_industry": r["industry"],
            "eegs_co2_t_fy2021": r["co2_2021"], "eegs_co2_t_fy2022": r["co2_2022"],
            "eegs_co2_t_fy2023": r["co2_2023"],
            "lat": pt.get("lat", ""), "lon": pt.get("lon", ""),
            "coord_precision": "municipality" if pt else "",
            "possible_duplicate_of": "", "source_type": ";".join(types),
            "source_ref": ";".join(refs),
        })
    n_eegs = len(out)
    for c in read_table("curated_sites.csv", sites_dir):
        row = {k: c.get(k, "") for k in SITE_FIELDS}
        row.update({"site_id": site_id("pub", c["site_name"]), "type_basis": "curated",
                    "identification_basis": "public_announcement"})
        out.append(row)
    seen: Dict[str, str] = {}
    for r in out:
        if not r["eegs_emitter_code"]:
            continue
        k = _dup_key(str(r["municipality"]), str(r["site_name"]))
        if k in seen:
            r["possible_duplicate_of"] = seen[k]
        else:
            seen[k] = str(r["site_id"])
    stats = {"eegs": n_eegs, "curated": len(out) - n_eegs,
             "confirmed": sum(1 for r in out if r["status"] == "confirmed"),
             "suspected": sum(1 for r in out if r["status"] == "suspected")}
    return out, stats
