"""substation_key normalisation."""
import pytest

from parse.names import substation_key


@pytest.mark.parametrize("raw,key", [
    ("鳥取変電所", "鳥取"),
    ("お茶の水(変)", "お茶ノ水"),
    ("木挽町（局配）", "木挽町"),
    ("北新得開閉所", "北新得"),
    ("新寺田66/22kV", "新寺田"),
    ("早月第一66/22kV", "早月第一"),
    ("中能登変電所（500kV）", "中能登"),
    ("与根　配変２号", "与根"),
    ("麻SS", "麻"),
    ("麻ss", "麻"),
    (" 西 通 変電所 ", "西通"),
    ("", ""),
])
def test_key_rules(raw, key):
    assert substation_key(raw) == key


@pytest.mark.parametrize("a,b", [
    ("霞ヶ関", "霞が関"),
    ("霞ヶ関", "霞ケ関"),
    ("霞ヵ関", "霞ケ関"),
    ("一ノ瀬", "一の瀬"),
    ("ｾﾝﾀｰ北(変)", "センター北"),
    ("ＡＢＣ変電所", "abc"),
])
def test_spelling_variants_fold(a, b):
    assert substation_key(a) == substation_key(b)


def test_distinct_names_stay_distinct():
    assert substation_key("北九州") != substation_key("北九州西")
