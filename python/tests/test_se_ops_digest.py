#!/usr/bin/env python3
"""Dependency-free assert-based tests for the se-copilot-ops-mcp-fed exec and region digests.
Run: python3 python/tests/test_se_ops_digest.py
No pytest — matches this repo's zero-non-stdlib-deps convention.

The fixtures below are REAL se-copilot-ops-mcp responses (get_open_pipeline with
group_by, get_winrate, get_top_deals stage="Lost"), captured live on 2026-10-08; the
region fixtures (EMEA-APAC) were captured live on 2026-10-12.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analyze
import render

# Real se-copilot-ops-mcp responses captured 2026-10-08 (trimmed: no _provenance/scope_note;
# top-deals cut to 3 rows).

BY_REGION = {'count': 860,
 'acv': {'value': 59511528.589999884, 'n': 860, 'of': 860, 'coverage': 1.0},
 'groups': [{'key': 'Brazil',
             'count': 206,
             'acv': {'value': 16712339.450000018, 'n': 206, 'of': 206, 'coverage': 1.0}},
            {'key': 'EMEA-APAC',
             'count': 95,
             'acv': {'value': 18441056.119999997, 'n': 95, 'of': 95, 'coverage': 1.0}},
            {'key': 'North LATAM',
             'count': 107,
             'acv': {'value': 3883121.919999999, 'n': 107, 'of': 107, 'coverage': 1.0}},
            {'key': 'South LATAM',
             'count': 424,
             'acv': {'value': 14842967.189999994, 'n': 424, 'of': 424, 'coverage': 1.0}},
            {'key': 'USA',
             'count': 28,
             'acv': {'value': 5632043.91, 'n': 28, 'of': 28, 'coverage': 1.0}}]}

BY_STAGE = {'count': 860,
 'acv': {'value': 59511528.589999884, 'n': 860, 'of': 860, 'coverage': 1.0},
 'groups': [{'key': 'Active Pursuit',
             'count': 157,
             'acv': {'value': 10481540.240000006, 'n': 157, 'of': 157, 'coverage': 1.0}},
            {'key': 'Commit & Signing',
             'count': 53,
             'acv': {'value': 3810184.59, 'n': 53, 'of': 53, 'coverage': 1.0}},
            {'key': 'Negotiate',
             'count': 80,
             'acv': {'value': 9602605.800000003, 'n': 80, 'of': 80, 'coverage': 1.0}},
            {'key': 'Proposal',
             'count': 102,
             'acv': {'value': 17667638.66, 'n': 102, 'of': 102, 'coverage': 1.0}},
            {'key': 'Qualification',
             'count': 180,
             'acv': {'value': 4479186.770000003, 'n': 180, 'of': 180, 'coverage': 1.0}},
            {'key': 'Scope & Validate',
             'count': 288,
             'acv': {'value': 13470372.530000001, 'n': 288, 'of': 288, 'coverage': 1.0}}]}

WR_H1 = {'by_count': {'won': 489,
              'lost': 627,
              'rate': 0.438,
              '_coverage': {'n': 1116, 'of': 1221, 'coverage': 0.914}},
 'by_acv': {'won_acv': 8353944.18,
            'lost_acv': 33493176.360000018,
            'rate': 0.2,
            '_coverage': {'n': 1116, 'of': 1116, 'coverage': 1.0}}}

WR_H2 = {'by_count': {'won': 236,
              'lost': 181,
              'rate': 0.566,
              '_coverage': {'n': 417, 'of': 918, 'coverage': 0.454}},
 'by_acv': {'won_acv': 6432463.480000002,
            'lost_acv': 11098280.57,
            'rate': 0.367,
            '_coverage': {'n': 417, 'of': 417, 'coverage': 1.0}}}

LOST_H1 = {'deals': [{'id': '006U600000R9gANIAZ',
            'name': 'CH - PMI - B2B',
            'region': 'EMEA-APAC',
            'acv': 1250000.0,
            'close_date': '2026-06-05',
            'stage_name': 'Lost'},
           {'id': '006U600000a7mfuIAA',
            'name': 'B2C AlGhurair Mega Mall Project 2.0',
            'region': 'EMEA-APAC',
            'acv': 1000000.0,
            'close_date': '2026-02-26',
            'stage_name': 'Lost'},
           {'id': '006U600000WcvNpIAJ',
            'name': 'US - Ace Hardware Corp - Sept 2025',
            'region': 'USA',
            'acv': 950000.0,
            'close_date': '2026-01-07',
            'stage_name': 'Lost'}]}

LOST_H2 = {'deals': [{'id': '006U600000ZUqRdIAL',
            'name': 'CAN - TD Bank - October 2025',
            'region': 'USA',
            'acv': 1270000.0,
            'close_date': '2026-07-02',
            'stage_name': 'Lost'},
           {'id': '006U6000014k8KjIAI',
            'name': 'US - Sleep Number - Aug 2026',
            'region': 'USA',
            'acv': 565000.0,
            'close_date': '2026-09-22',
            'stage_name': 'Lost'},
           {'id': '006U600000oqUDLIA2',
            'name': 'US - Dollar Tree - March 2026',
            'region': 'USA',
            'acv': 490000.0,
            'close_date': '2026-07-21',
            'stage_name': 'Lost'}]}

TODAY = "2026-10-08"
WINDOWS = [
    {"label": "H2 2026", "start": "2026-07-01", "end": "2026-12-31", "winrate": WR_H2, "lost": LOST_H2},
    {"label": "H1 2026", "start": "2026-01-01", "end": "2026-06-30", "winrate": WR_H1, "lost": LOST_H1},
]
STAGES = {"Qualification", "Scope & Validate", "Active Pursuit", "Proposal", "Negotiate", "Commit & Signing"}


def _digest(stale=None):
    return analyze.exec_digest_from_se_ops(TODAY, BY_REGION, BY_STAGE, WINDOWS, stale=stale)


def test_pipeline_overall_matches_mcp_totals_and_stages():
    d = _digest()["pipeline_overall"]
    assert d["open_count"] == BY_STAGE["count"]
    assert d["open_acv"] == round(BY_STAGE["acv"]["value"])
    assert set(d["by_stage"]) == STAGES
    assert sum(c["count"] for c in d["by_stage"].values()) == d["open_count"]
    assert abs(sum(c["acv"] for c in d["by_stage"].values()) - d["open_acv"]) <= len(STAGES)


def test_region_blocks_carry_acv_coverage_and_sum_to_total():
    prs = _digest()["pipeline_region_stage"]
    assert set(prs) == {g["key"] for g in BY_REGION["groups"]}
    assert sum(b["open_count"] for b in prs.values()) == BY_REGION["count"]
    for b in prs.values():
        assert b["_coverage"]["value"] == "open pipeline" and b["_coverage"]["coverage"] == 1.0
        assert b["by_stage"] == {}


def test_winrate_blocks_newest_first_with_strict_equal_sensitivity():
    tr = _digest()["org_winrate_trend"]
    assert list(tr) == ["H2 2026", "H1 2026"]
    h1 = tr["H1 2026"]
    assert (h1["won"], h1["lost"]) == (WR_H1["by_count"]["won"], WR_H1["by_count"]["lost"])
    assert h1["strict"] == h1["sensitivity"] == WR_H1["by_count"]["rate"]
    assert h1["window"] == {"from": "2026-01-01", "to": "2026-06-30"}
    assert h1["acv_rate"] == WR_H1["by_acv"]["rate"]


def test_top_lost_mapped_to_the_fields_the_template_reads():
    top = _digest()["org_winrate_trend"]["H1 2026"]["top_lost"]
    assert [t["name"] for t in top] == [d["name"] for d in LOST_H1["deals"]]
    src = LOST_H1["deals"][0]
    assert top[0] == {"projectId": src["id"], "name": src["name"], "macro": src["region"],
                      "closed": src["close_date"], "acv": src["acv"]}
    assert all("2026-01-01" <= t["closed"] <= "2026-06-30" for t in top)


def test_rate_is_none_when_no_decided_deals():
    empty = {"by_count": {"won": 0, "lost": 0, "rate": None, "_coverage": {"n": 0, "of": 5, "coverage": 0.0}},
             "by_acv": {"won_acv": 0, "lost_acv": 0, "rate": None}}
    d = analyze.exec_digest_from_se_ops(
        TODAY, BY_REGION, BY_STAGE,
        [{"label": "custom", "start": "2026-11-01", "end": "2026-11-30", "winrate": empty, "lost": {"deals": []}}])
    w = d["org_winrate_trend"]["custom"]
    assert w["strict"] is None and w["won"] == 0 and w["top_lost"] == []


def test_blocks_the_mcp_cannot_supply_are_absent_not_faked():
    d = _digest()
    assert "data_quality_scorecard" not in d and "orphan_rocketlane_projects" not in d
    assert "movement" not in d
    assert d["se_by_phase"]["columns"] == analyze.SE_BY_PHASE_COLUMNS and d["se_by_phase"]["rows"] == []


def test_caveat_names_the_source_and_flags_a_stale_sync():
    assert "se-copilot-ops-mcp" in _digest()["caveat"]
    assert "stale" not in _digest({"stale": False, "gap_days": 0})["caveat"]
    c = _digest({"stale": True, "gap_days": 9})["caveat"]
    assert "stale" in c and "9 day" in c


def test_digest_embeds_in_the_artifact_with_a_valid_checksum():
    d = _digest()
    json.dumps(d, sort_keys=True)
    html = render.build_artifact("exec", d, {"source": "se-copilot-ops-mcp", "as_of": TODAY}, "2026-10-08T00:00:00")
    assert 'data-view="exec"' in html and "se-copilot-ops-mcp" in html


# --- Region digest (EMEA-APAC, captured live 2026-10-12) ----------------------------

R_TODAY = "2026-10-12"

R_BY_STAGE = {'count': 92,
 'acv': {'value': 17627712.03999999, 'n': 92, 'of': 92, 'coverage': 1},
 'groups': [{'key': 'Active Pursuit', 'count': 18, 'acv': {'value': 2474088.38, 'n': 18, 'of': 18, 'coverage': 1}},
            {'key': 'Commit & Signing', 'count': 9, 'acv': {'value': 1736892.01, 'n': 9, 'of': 9, 'coverage': 1}},
            {'key': 'Negotiate', 'count': 7, 'acv': {'value': 825399.99, 'n': 7, 'of': 7, 'coverage': 1}},
            {'key': 'Proposal', 'count': 14, 'acv': {'value': 5106173.88, 'n': 14, 'of': 14, 'coverage': 1}},
            {'key': 'Qualification', 'count': 23, 'acv': {'value': 1943007.28, 'n': 23, 'of': 23, 'coverage': 1}},
            {'key': 'Scope & Validate', 'count': 21, 'acv': {'value': 5542150.499999999, 'n': 21, 'of': 21, 'coverage': 1}}]}

R_TOP = {'deals': [
    {'id': '006U6000006nO0vIAE', 'name': 'B2C MKP - Santander', 'region': 'EMEA-APAC', 'acv': 1755800.12, 'close_date': '2027-06-30', 'stage_name': 'Proposal'},
    {'id': '006U6000012U0grIAC', 'name': 'MKP - Worten PT', 'region': 'EMEA-APAC', 'acv': 1170533.41, 'close_date': '2027-12-31', 'stage_name': 'Scope & Validate'},
    {'id': '006U600000ZlDiQIAV', 'name': 'B2C - Sport Vision', 'region': 'EMEA-APAC', 'acv': 1163510.21, 'close_date': '2027-07-31', 'stage_name': 'Scope & Validate'},
    {'id': '006U600000nhAhlIAE', 'name': 's.Oliver Group - Scayle replatforming', 'region': 'EMEA-APAC', 'acv': 837689.89, 'close_date': '2027-03-31', 'stage_name': 'Proposal'},
    {'id': '006U600000z7gVfIAI', 'name': 'B2C — Fourlis Cashdesk (IKEA, Intersport, Footlocker)', 'region': 'EMEA-APAC', 'acv': 755877.85, 'close_date': '2027-03-01', 'stage_name': 'Commit & Signing'}]}

R_OVERDUE = {'count': 21, 'acv': {'value': 208995.03, 'n': 21, 'of': 21, 'coverage': 1}}

R_OVERDUE_TOP = {'deals': [
    {'id': '006U600000tiOqCIAU', 'name': 'UK - The Football Association - B2C Commerce', 'region': 'EMEA-APAC', 'acv': 101645.26, 'close_date': '2026-09-30', 'stage_name': 'Scope & Validate'},
    {'id': '006U600000ox8UcIAI', 'name': 'B2C - SL Benfica PT', 'region': 'EMEA-APAC', 'acv': 93642.67, 'close_date': '2026-09-30', 'stage_name': 'Active Pursuit'},
    {'id': '006U600000pGtrBIAS', 'name': 'WL accounts - OBI International Phase 2', 'region': 'EMEA-APAC', 'acv': 10183.64, 'close_date': '2026-03-27', 'stage_name': 'Commit & Signing'}]}


def _region(top=R_TOP, rl_items=None, stale=None):
    return analyze.region_digest_from_se_ops("EMEA-APAC", R_TODAY, R_BY_STAGE, top, R_OVERDUE, R_OVERDUE_TOP,
                                             rl_items=rl_items, stale=stale)


def test_region_funnel_matches_mcp_totals():
    f = _region()["funnel"]
    assert f["open_count"] == 92 and f["open_acv"] == round(R_BY_STAGE["acv"]["value"])
    assert set(f["by_stage"]) == STAGES
    assert sum(c["count"] for c in f["by_stage"].values()) == 92


def test_region_top_opps_carry_health_and_a_summary_of_the_shown_rows():
    to = _region()["top_opps"]
    assert [o["name"] for o in to["top"]] == [d["name"] for d in R_TOP["deals"]]
    assert all(o["severity"] == "green" for o in to["top"])
    assert to["summary"] == {"red": 0, "yellow": 0, "green": 5}
    assert to["top"][0]["stage"] == "Proposal" and to["top"][0]["closed_forecast"] == "2027-06-30"


def test_region_health_flags_overdue_closing_soon_and_missing_acv():
    deals = {"deals": [
        {"id": "a", "name": "past", "region": "EMEA-APAC", "acv": 10.0, "close_date": "2026-10-01", "stage_name": "Proposal"},
        {"id": "b", "name": "soon", "region": "EMEA-APAC", "acv": 10.0, "close_date": "2026-10-20", "stage_name": "Proposal"},
        {"id": "c", "name": "no acv", "region": "EMEA-APAC", "acv": 0, "close_date": "2027-01-01", "stage_name": "Proposal"}]}
    top = {o["name"]: o for o in _region(top=deals)["top_opps"]["top"]}
    assert top["past"]["severity"] == "red" and top["past"]["flags"] == ["overdue 11d"]
    assert top["soon"]["severity"] == "yellow" and top["soon"]["flags"] == ["closing in 8d"]
    assert top["no acv"]["severity"] == "yellow" and top["no acv"]["flags"] == ["no ACV"]


def test_region_at_risk_is_the_overdue_count_acv_and_top_rows():
    ov = _region()["at_risk_overdue"]
    assert ov["count"] == 21 and ov["acv"] == 208995
    assert [o["projectId"] for o in ov["opps"]] == [d["id"] for d in R_OVERDUE_TOP["deals"]]
    assert all(o["closed_forecast"] < R_TODAY for o in ov["opps"])


def test_region_blocks_the_mcp_cannot_supply_are_absent():
    d = _region()
    for k in ("se_by_stage", "hygiene_by_se", "no_stage", "movement", "orphan_rocketlane_projects"):
        assert k not in d, k


def test_region_se_by_phase_only_counts_that_regions_projects():
    rl = [("1", {"macro": "EMEA-APAC", "owner": "Ana", "status": "On Hold", "name": "x"}),
          ("2", {"macro": "Brazil", "owner": "Bia", "status": "On Hold", "name": "y"})]
    rows = _region(rl_items=rl)["se_by_phase"]["rows"]
    assert [r["owner"] for r in rows] == ["Ana"]


def test_region_digest_embeds_in_the_artifact():
    html = render.build_artifact("region", _region(),
                                 {"source": "se-copilot-ops-mcp", "as_of": R_TODAY}, "2026-10-12T00:00:00")
    assert 'data-view="region"' in html


ALL_TESTS = [v for k, v in sorted(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    failures = 0
    for t in ALL_TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(ALL_TESTS) - failures}/{len(ALL_TESTS)} passed")
    sys.exit(1 if failures else 0)
