"""Substation name normalisation shared by the load and capacity tables.

substation_key(name) produces the join key used to match a loading-file column to a row of the
capacity table of the same operator. Rules, applied in order:
  1. Unicode NFKC (full-width ASCII and half-width katakana become their standard forms).
  2. Remove all whitespace.
  3. Remove bracketed annotations: (...), [...], {...}, 〔...〕, 【...】, 「...」, 『...』, <...>.
     This also removes the "(変)" substation marker.
  4. Remove voltage annotations such as "66kV", "66/22kV", "154/66/22kV", "22-13.8kV".
  5. Remove trailing facility words repeatedly: 変電所, 開閉所, 変換所, SS, S/S,
     配変N号 / 配変N (distribution transformer number).
  6. Fold common spelling variants: ヶ/ヵ/が -> ケ, の -> ノ.
  7. Upper-case ASCII letters.
An empty result is returned as "".
"""
from __future__ import annotations

import re
import unicodedata

_BRACKETS = re.compile(r"\([^()]*\)|\[[^\[\]]*\]|\{[^{}]*\}|〔[^〔〕]*〕|【[^【】]*】|「[^「」]*」|『[^『』]*』|<[^<>]*>")
_VOLTAGE = re.compile(r"\d+(?:\.\d+)?(?:[/\-・,]\d+(?:\.\d+)?)*KV", re.IGNORECASE)
_SUFFIX = re.compile(r"(?:変電所|開閉所|変換所|配変\d*号?|S/S|SS)$", re.IGNORECASE)
_FOLD = str.maketrans({"ヶ": "ケ", "ヵ": "ケ", "が": "ケ", "の": "ノ"})


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s or "")


def substation_key(name: str) -> str:
    s = nfkc(name)
    s = re.sub(r"\s+", "", s)
    prev = None
    while prev != s:  # nested or repeated brackets
        prev = s
        s = _BRACKETS.sub("", s)
    s = _VOLTAGE.sub("", s)
    prev = None
    while prev != s:
        prev = s
        s = _SUFFIX.sub("", s)
    s = s.translate(_FOLD)
    return s.upper()
