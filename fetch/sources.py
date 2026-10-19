"""Per-operator entry pages and link-selection rules.

Each rule is (kind, href_regex, text_regex). An anchor is selected when its resolved URL path
matches href_regex and, if text_regex is given, its NFKC-normalised link text matches text_regex.
kinds: load_tr (hourly transformer loading results), capacity_tr (transformer capacity table).
"""
from __future__ import annotations

import posixpath
import re
import unicodedata
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

FY_RE = re.compile(r"(20\d{2})年度")


@dataclass
class Anchor:
    href: str
    text: str
    heading: str
    fy_hint: str  # most recent "YYYY年度" seen in page text before the anchor


@dataclass
class Target:
    operator: str
    kind: str
    url: str
    local_name: str
    note: str = ""


@dataclass
class Source:
    pages: List[str]
    rules: List[Tuple[str, str, Optional[str]]]
    unpublished: List[Tuple[str, str, str]] = field(default_factory=list)  # (kind, url, status)


class _AnchorParser(HTMLParser):
    HEAD_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6", "dt", "th", "caption"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: List[Anchor] = []
        self._href: Optional[str] = None
        self._text: List[str] = []
        self._in_head = False
        self._head_text: List[str] = []
        self.heading = ""
        self.fy_hint = ""

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self._href, self._text = href, []
        if tag == "area":  # image-map links: the link text is the alt attribute
            a = dict(attrs)
            if a.get("href"):
                self.anchors.append(Anchor(a["href"], (a.get("alt") or "").strip(),
                                           self.heading, self.fy_hint))
        if tag in self.HEAD_TAGS:
            self._in_head, self._head_text = True, []

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._text)).strip()
            self.anchors.append(Anchor(self._href, text, self.heading, self.fy_hint))
            self._href = None
        if tag in self.HEAD_TAGS and self._in_head:
            self._in_head = False
            self.heading = re.sub(r"\s+", " ", "".join(self._head_text)).strip()[:80]

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)
        if self._in_head:
            self._head_text.append(data)
        m = None
        for m in FY_RE.finditer(data):
            pass
        if m is not None and self._href is None:
            self.fy_hint = m.group(1)


def parse_anchors(html_text: str) -> List[Anchor]:
    p = _AnchorParser()
    p.feed(html_text)
    return p.anchors


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


SOURCES: Dict[str, Source] = {
    "hokkaido": Source(
        pages=["https://www.hepco.co.jp/network/con_service/public_document/bid_info.html"],
        rules=[
            ("load_tr", r"/zip/tide_results_trans(former|_\d+)\.zip$", None),
            ("capacity_tr", r"/zip/sys_capa_(kikan|local\d+)\.zip$", None),
        ],
    ),
    "tohoku": Source(
        pages=[
            "https://nw.tohoku-epco.co.jp/consignment/system/demand/",
            "https://nw.tohoku-epco.co.jp/consignment/system/announcement/",
        ],
        rules=[
            ("load_tr", r"/data/jisseki_\w+?_tr_\d{4}_\d+\.csv$", None),
            ("load_tr", r"/data/ju-sohai_[\w-]+\.csv$", r"変圧器"),
            ("capacity_tr", r"/data/sys_capa_\w+?_tr_\d+_\d+\.csv$", None),
        ],
    ),
    "tepco": Source(
        pages=["https://www.tepco.co.jp/pg/consignment/system/"],
        rules=[
            ("load_tr", r"/tyouryu_(kikan|154kV|66kV)\.zip$", None),
            ("capacity_tr", r"/csv_yosochoryu_\w+\.zip$", None),
        ],
    ),
    "chubu": Source(
        pages=["https://powergrid.chuden.co.jp/goannai/hatsuden_kouri/takuso_kyokyu/rule/"],
        rules=[("load_tr", r"\.(xlsx|xlsm|xls|csv)$", r"潮流実績\(変圧器\)")],
        unpublished=[("capacity_tr", "https://gridmap.powergrid.chuden.co.jp/",
                      "not_published_as_file")],
    ),
    "hokuriku": Source(
        pages=["https://www.rikuden.co.jp/nw_notification/U_154seiyaku.html"],
        rules=[
            ("load_tr", r"/attach/(juyou\d{4}|jisseki_\w+?_tr_\d{4}(_\d+)?)\.csv$", r"変圧器"),
            ("capacity_tr", r"/attach/sys_capa_\w+?_tr_\d+_\d+\.csv$", None),
        ],
    ),
    "kansai": Source(
        pages=["https://www.kansai-td.co.jp/consignment/disclosure/distribution-equipment/index.html"],
        rules=[
            ("load_tr", r"/01_chouryu_Tr_\d{4}(_154more)?\.csv$", None),
            ("capacity_tr", r"/154kv_(more|less)_trans\.csv$", None),
        ],
    ),
    "chugoku": Source(
        pages=["https://www.energia.co.jp/nw/service/retailer/keitou/access/"],
        rules=[
            ("load_tr", r"/csv/jisseki_\w+?_tr_\d{4}_\d+\.csv$", None),
            ("capacity_tr", r"/zip/csv_\w+\.zip$", None),
        ],
    ),
    "shikoku": Source(
        pages=["https://www.yonden.co.jp/nw/line_access/data.html"],
        rules=[
            ("load_tr", r"/(jisseki_\w+?_tr_\d{4}_\d+|tr_chouryu_[\w-]+)\.csv$", None),
            ("capacity_tr", r"/data/sys_capa_\w+?_tr_\d+_\d+\.csv$", None),
        ],
    ),
    "kyushu": Source(
        pages=["https://www.kyuden.co.jp/td/service/wheeling/disclosure.html"],
        rules=[
            ("load_tr", r"\.(csv|xlsx|xls)$", r"潮流実績\(変圧器\)"),
            ("capacity_tr", r"\.zip$", r"変圧器CSV"),
        ],
    ),
    "okinawa": Source(
        pages=[
            "https://www.okiden.co.jp/business-support/service/juyo-and-sohaiden/",
            "https://www.okiden.co.jp/business-support/service/juyo-and-sohaiden/jisseki1/index.html",
            "https://www.okiden.co.jp/business-support/service/juyo-and-sohaiden/local-jisseki/index.html",
        ],
        rules=[
            ("load_tr", r"/juyo-and-sohaiden/tyoryujisseki_\w+\.(csv|xlsx)$", None),
            ("load_tr", r"/local-jisseki/tyoryu_\w+\.(csv|xlsx)$", None),
            ("capacity_tr", r"/sys_yoso_(kikan|local)_tr\.csv$", None),
        ],
    ),
}

OPERATORS = list(SOURCES)


def select_targets(operator: str, page_url: str, html_text: str) -> List[Target]:
    src = SOURCES[operator]
    out: List[Target] = []
    for a in parse_anchors(html_text):
        url = urljoin(page_url, a.href.strip())
        path = urlparse(url).path
        text = nfkc(a.text)
        for kind, href_re, text_re in src.rules:
            if not re.search(href_re, path):
                continue
            if text_re and not re.search(text_re, text):
                continue
            base = posixpath.basename(path)
            note = "; ".join(x for x in (
                f"text={text}" if text else "",
                f"heading={nfkc(a.heading)}" if a.heading else "",
                f"fy_hint={a.fy_hint}" if a.fy_hint else "",
            ) if x)
            out.append(Target(operator, kind, url, f"{operator}/{kind}/{base}", note))
            break
    # de-duplicate by URL (same link repeated on a page), keep first
    seen, uniq = set(), []
    for t in out:
        if t.url not in seen:
            seen.add(t.url)
            uniq.append(t)
    return uniq
