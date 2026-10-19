"""Join substation-year loading statistics to the capacity tables and reconstruct load-direction
headroom under two definitions:

  headroom_naive_mw = operating_mw - peak_mw
  headroom_n1_mw    = (units - 1) / units * rated_mw - peak_mw     (units >= 2; else empty)

peak_mw is the coincident annual peak of the substation-year series (see stats.py).

Join rules (same operator, same substation_key; voltages compared with 6/6.6/6.9 kV as one class):
  matched_key_v2      the load group has a secondary voltage: all capacity rows of the key with
                      the same secondary voltage are summed (units, rated, operating).
  matched_key_v1      the load group has no secondary voltage (published per primary-voltage
                      group): all capacity rows of the key whose primary voltage belongs to that
                      group are summed. Group membership: the same primary voltage; for TEPCO the
                      66 kV group also takes rows with blank voltage (distribution substations,
                      voltage not published) and the bulk group (blank) takes 500 and 275 kV rows.
  unmatched_voltage   the key exists in the capacity table but no row has a matching voltage.
  unmatched_key       the key does not exist in the capacity table.
  unnamed_column      the loading column has no substation name (key starts with '#').
  no_capacity_table   the operator publishes no capacity file.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from parse.common import kv_join_key

HEADROOM_FIELDS = ["operator", "fiscal_year", "substation_key", "substation_raw", "v1_kv",
                   "v2_kv", "join_status", "n_capacity_rows", "capacity_category", "units",
                   "rated_mw", "operating_mw", "n1_capacity_mw", "peak_mw", "peak_ts_local",
                   "valid_hours", "hours_in_year", "headroom_naive_mw", "headroom_n1_mw",
                   "n1_note", "capacity_as_of"]
JOIN_REPORT_FIELDS = ["operator", "fiscal_year", "is_latest_year", "load_groups",
                      "named_load_groups", "matched", "matched_key_v2", "matched_key_v1",
                      "unmatched_voltage", "unmatched_key", "unnamed_column",
                      "no_capacity_table", "match_rate_named", "capacity_rows",
                      "capacity_rows_matched", "capacity_match_rate"]

V1_GROUPS = {("tepco", "66"): {"66", ""}, ("tepco", ""): {"500", "275"}}


def _num(x) -> Optional[float]:
    if x is None or x == "":
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _index_capacity(cap_rows: List[dict]) -> Dict[Tuple[str, str], List[int]]:
    idx: Dict[Tuple[str, str], List[int]] = defaultdict(list)
    for i, r in enumerate(cap_rows):
        if r.get("substation_key") and not str(r["substation_key"]).startswith("#"):
            idx[(r["operator"], r["substation_key"])].append(i)
    return idx


def _select(op: str, st: dict, cand: List[int], cap_rows: List[dict]) -> Tuple[str, List[int]]:
    v2 = kv_join_key(st.get("v2_kv", ""))
    if v2:
        rows = [i for i in cand if kv_join_key(cap_rows[i]["v2_kv"]) == v2]
        return ("matched_key_v2" if rows else "unmatched_voltage"), rows
    v1_set = {s for s in str(st.get("v1_kv", "")).split(";")}
    allowed = set()
    for v1 in v1_set:
        allowed |= V1_GROUPS.get((op, v1), {v1} if v1 else set())
    rows = [i for i in cand if cap_rows[i]["v1_kv"] in allowed]
    return ("matched_key_v1" if rows else "unmatched_voltage"), rows


def reconstruct(stations: List[dict], cap_rows: List[dict],
                operators_without_capacity: set) -> Tuple[List[dict], List[dict]]:
    """Return (headroom rows, join report rows)."""
    cap_idx = _index_capacity(cap_rows)
    latest: Dict[str, int] = {}
    for s in stations:
        latest[s["operator"]] = max(latest.get(s["operator"], 0), int(s["fiscal_year"]))
    out: List[dict] = []
    matched_cap: Dict[Tuple[str, int], set] = defaultdict(set)
    for s in stations:
        op, key = s["operator"], s["substation_key"]
        rows: List[int] = []
        if op in operators_without_capacity:
            status = "no_capacity_table"
        elif key.startswith("#") or not key:
            status = "unnamed_column"
        elif (op, key) not in cap_idx:
            status = "unmatched_key"
        else:
            status, rows = _select(op, s, cap_idx[(op, key)], cap_rows)
        rec = {k: s.get(k) for k in ("operator", "fiscal_year", "substation_key", "substation_raw",
                                     "v1_kv", "v2_kv", "peak_mw", "peak_ts_local",
                                     "valid_hours", "hours_in_year")}
        rec.update({"join_status": status, "n_capacity_rows": len(rows), "capacity_category": "",
                    "units": None, "rated_mw": None, "operating_mw": None,
                    "n1_capacity_mw": None, "headroom_naive_mw": None, "headroom_n1_mw": None,
                    "n1_note": "", "capacity_as_of": ""})
        if rows:
            # one group listed in two regional files: rows with identical voltages, units and capacities
            # matched to the same load series are counted once
            seen_sig, uniq = set(), []
            for i in rows:
                sig = tuple(str(cap_rows[i].get(f, "")) for f in ("v1_kv", "v2_kv", "units", "rated_mw", "operating_mw"))
                if sig not in seen_sig:
                    seen_sig.add(sig)
                    uniq.append(i)
            rows = uniq
            rec["n_capacity_rows"] = len(rows)
            matched_cap[(op, int(s["fiscal_year"]))].update(rows)
            units = [_num(cap_rows[i]["units"]) for i in rows]
            rated = [_num(cap_rows[i]["rated_mw"]) for i in rows]
            oper = [_num(cap_rows[i]["operating_mw"]) for i in rows]
            u = sum(units) if all(x is not None for x in units) else None
            rt = sum(rated) if all(x is not None for x in rated) else None
            op_mw = sum(oper) if all(x is not None for x in oper) else None
            cats = sorted({cap_rows[i]["category"] for i in rows if cap_rows[i]["category"]})
            notes = []
            if len(rows) > 1:
                notes.append("aggregated_rows")
            n1 = None
            if u is None or rt is None:
                notes.append("units_or_rated_missing")
            elif u < 2:
                notes.append("single_unit")
            else:
                n1 = (u - 1) / u * rt
            peak = _num(s.get("peak_mw"))
            rec.update({
                "capacity_category": ";".join(cats),
                "units": int(u) if u is not None else None, "rated_mw": rt,
                "operating_mw": op_mw, "n1_capacity_mw": round(n1, 3) if n1 is not None else None,
                "headroom_naive_mw": round(op_mw - peak, 3) if (op_mw is not None and peak is not None) else None,
                "headroom_n1_mw": round(n1 - peak, 3) if (n1 is not None and peak is not None) else None,
                "n1_note": ";".join(notes),
                "capacity_as_of": ";".join(sorted({str(cap_rows[i]["as_of"]) for i in rows if cap_rows[i]["as_of"]})),
            })
        out.append(rec)
    # report
    counts: Dict[Tuple[str, int], Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in out:
        c = counts[(r["operator"], int(r["fiscal_year"]))]
        c["load_groups"] += 1
        c[r["join_status"]] += 1
    cap_per_op: Dict[str, int] = defaultdict(int)
    for r in cap_rows:
        cap_per_op[r["operator"]] += 1
    report: List[dict] = []
    for (op, fy), c in sorted(counts.items()):
        matched = c["matched_key_v2"] + c["matched_key_v1"]
        named = c["load_groups"] - c["unnamed_column"]
        ncap = cap_per_op.get(op, 0)
        nmc = len(matched_cap.get((op, fy), set()))
        report.append({
            "operator": op, "fiscal_year": fy, "is_latest_year": fy == latest.get(op),
            "load_groups": c["load_groups"], "named_load_groups": named, "matched": matched,
            "matched_key_v2": c["matched_key_v2"], "matched_key_v1": c["matched_key_v1"],
            "unmatched_voltage": c["unmatched_voltage"], "unmatched_key": c["unmatched_key"],
            "unnamed_column": c["unnamed_column"], "no_capacity_table": c["no_capacity_table"],
            "match_rate_named": round(matched / named, 4) if named and op not in operators_without_capacity else None,
            "capacity_rows": ncap, "capacity_rows_matched": nmc,
            "capacity_match_rate": round(nmc / ncap, 4) if ncap else None,
        })
    return out, report
