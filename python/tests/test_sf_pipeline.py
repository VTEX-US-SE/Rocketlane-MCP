#!/usr/bin/env python3
"""Dependency-free assert-based tests for the Salesforce weekly pipeline import.
Run: python3 python/tests/test_sf_pipeline.py
No pytest — matches this repo's zero-non-stdlib-deps convention.

Fixture rows are copied verbatim (header + real rows) from the validated weekly export
at the Drive-synced path (SF_PIPELINE_PATH), captured 2026-08-17: RedSea Global Saudi,
Ethara F1 Merchandise, and the "Rubis Energy Kenya" discrepancy case (Rocketlane shows
this deal at $20M; Salesforce says $67,003.93 — the finding that motivated this feature).
Edge-case rows (Carlos Rivero->Carlos Celis mapping, an unmapped owner, an unmapped
country, blank amount/date, a duplicate id) are appended synthetically.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analyze

HEADER = ("Assigned SE,Stage,Opportunity Name,Owner Role,Account Name,Fiscal Period,"
          "Amount,Probability (%),Age,Created Date,Type,Forecast Category,ACV Preview,"
          "ACV Preview (USD),Close Date (2),Close Date,Total Sales Cycle Age,"
          "Sales Region,Lost Reason,Why did we lose?,Opportunity ID,Opportunity ID")

REDSEA = ('Diego cione,Commit & Signing,RedSea Global Saudi B2B Marketplace,'
          'EMEA/APAC Sales Leader,RedSea Global,Q3-2026,"USD 485,000.00",90%,305,'
          '16/10/2025,New Client,Commit,"USD 431,666.67","431,666.67",30/09/2026,'
          '30/09/2026,305,Middle East and Africa,-,-,006U600000ZFcGz,006U600000ZFcGzIAL')

ETHARA = ('Diego cione,Qualification,Ethara B2C/B2B Formula 1 Merchandise,'
          'EMEA/APAC Sales Leader,Ethara,Q4-2026,"USD 500,000.00",5%,293,28/10/2025,'
          'New Client,Not Forecasted,"USD 500,000.00","500,000.00",31/12/2026,'
          '31/12/2026,293,Middle East and Africa,-,-,006U600000a552N,006U600000a552NIAQ')

RUBIS = ('William Jeanne,Proposal,B2C / B2B Rubis kenya Grocery,EMEA/APAC Sales Leader,'
         'Rubis Energy,Q4-2026,"USD 144,000.00",50%,46,02/07/2026,New Client,Best Case,'
         '"USD 67,003.93","67,003.93",31/10/2026,31/10/2026,46,'
         'Middle East and Africa,-,-,006U600000zOBdV,006U600000zOBdVIAW')

# Edge cases (synthetic, exercising mapping/parsing paths not hit by the 3 real rows above)
RIVERO = ('Carlos Rivero,Won,Test Rivero Deal,EMEA/APAC Sales,Test Account,Q3-2026,'
          '"EUR 10,000.00",100%,10,01/01/2026,New Client,Won,"EUR 10,000.00","11,000.00",'
          '01/03/2026,01/03/2026,10,France,-,-,006TESTRIVER01A,006TESTRIVER01AIAA')

UNMAPPED_OWNER = ('New Hire Test,Proposal,Some Deal,US Sales,Some Account,Q3-2026,'
                   '"USD 5,000.00",50%,5,01/01/2026,New Client,Stretch,"USD 5,000.00",'
                   '"5,000.00",01/03/2026,01/03/2026,5,United States,-,-,'
                   '006TESTUNMAP01A,006TESTUNMAP01AIAA')

UNMAPPED_COUNTRY = ('Noe Eustaquio,Qualification,Some Deal 2,North LATAM Leader,'
                     'Some Account 2,Q3-2026,"USD 1,000.00",5%,1,01/01/2026,New Client,'
                     'Not Forecasted,"USD 1,000.00","1,000.00",01/03/2026,01/03/2026,1,'
                     'Atlantis,-,-,006TESTUNMAP02A,006TESTUNMAP02AIAA')

BLANK_ROW = ('Noe Eustaquio,Lost,Some Deal 3,North LATAM Leader,Some Account 3,Q3-2026,-,'
             '0%,1,01/01/2026,New Client,Not Forecasted,USD 0.00,0,-,-,1,Mexico,Timing,-,'
             '006TESTBLANK01A,006TESTBLANK01AIAA')

DUPLICATE_ROW = ('Diego cione,Won,Duplicate of RedSea,EMEA/APAC Sales Leader,RedSea Global,'
                  'Q3-2026,"USD 1.00",100%,1,01/01/2026,New Client,Won,"USD 1.00","1.00",'
                  '01/03/2026,01/03/2026,1,Middle East and Africa,-,-,'
                  '006U600000ZFcGz,006U600000ZFcGzIAL')

FULL_CSV = "\n".join([HEADER, REDSEA, ETHARA, RUBIS, RIVERO, UNMAPPED_OWNER,
                       UNMAPPED_COUNTRY, BLANK_ROW, DUPLICATE_ROW]) + "\n"


def _find(items, sfid_raw):
    key = analyze.norm_sfid(sfid_raw)
    for k, r in items:
        if k == key:
            return r
    return None


def test_redsea_row_shape_and_values():
    items, _ = analyze.parse_sf_pipeline_csv(HEADER + "\n" + REDSEA + "\n")
    r = _find(items, "006U600000ZFcGz")
    assert r is not None, items
    assert r["stage"] == "Commit & Signing", r
    assert r["acv"] == 431666.67, r
    assert r["owner"] == "Diego Cione", r  # "Diego cione" -> mapped
    assert r["macro"] == "EMEA-APAC", r
    assert r["closed"] == "2026-09-30", r
    assert r["status"] == "", r  # open stage -> not "Completed"
    # every field pipeline()/scorecard()/opp_health() read must exist
    for field in ("name", "archived", "stage", "closed", "acv", "gmv", "sfid", "loss",
                  "cancel", "region", "macro", "status", "owner"):
        assert field in r, f"missing field {field}"


def test_rubis_discrepancy_case():
    """The exact case that motivated this feature: Rocketlane shows this deal at
    ACV $20,000,000; Salesforce says $67,003.93. Confirms the parser gets the real
    (small) number, owner williamjeanne, stage Proposal."""
    items, _ = analyze.parse_sf_pipeline_csv(HEADER + "\n" + RUBIS + "\n")
    r = _find(items, "006U600000zOBdV")
    assert r is not None
    assert r["acv"] == 67003.93, r
    assert r["owner"] == "williamjeanne", r
    assert r["stage"] == "Proposal", r


def test_status_defaults_completed_for_won_lost_only():
    won_row = ETHARA.replace("Qualification", "Won")
    items, _ = analyze.parse_sf_pipeline_csv(HEADER + "\n" + won_row + "\n")
    r = _find(items, "006U600000a552N")
    assert r["status"] == "Completed", r
    items2, _ = analyze.parse_sf_pipeline_csv(HEADER + "\n" + ETHARA + "\n")  # Qualification
    r2 = _find(items2, "006U600000a552N")
    assert r2["status"] == "", r2


def test_carlos_rivero_maps_to_carlos_celis():
    items, _ = analyze.parse_sf_pipeline_csv(HEADER + "\n" + RIVERO + "\n")
    r = _find(items, "006TESTRIVER01A")
    assert r["owner"] == "Carlos Celis", r


def test_unmapped_owner_passes_through_and_is_reported():
    items, report = analyze.parse_sf_pipeline_csv(HEADER + "\n" + UNMAPPED_OWNER + "\n")
    r = _find(items, "006TESTUNMAP01A")
    assert r["owner"] == "New Hire Test", r  # passed through, not dropped
    assert "New Hire Test" in report["unmapped_owners"], report


def test_unmapped_country_falls_back_to_no_region_and_is_reported():
    items, report = analyze.parse_sf_pipeline_csv(HEADER + "\n" + UNMAPPED_COUNTRY + "\n")
    r = _find(items, "006TESTUNMAP02A")
    assert r["macro"] == "(no region)", r
    assert r["region"] == "Atlantis", r
    assert "Atlantis" in report["unmapped_regions"], report


def test_blank_amount_and_date_parse_to_none_and_empty():
    items, _ = analyze.parse_sf_pipeline_csv(HEADER + "\n" + BLANK_ROW + "\n")
    r = _find(items, "006TESTBLANK01A")
    assert r["closed"] == "", r  # "-" close date
    assert r["acv"] == 0.0, r  # "USD 0.00" in ACV Preview (USD) -> 0.0, not None


def test_duplicate_sfid_detected():
    items, report = analyze.parse_sf_pipeline_csv(HEADER + "\n" + REDSEA + "\n" + DUPLICATE_ROW + "\n")
    key = analyze.norm_sfid("006U600000ZFcGz")
    assert report["duplicate_sfids"] == [key], report
    assert len(items) == 2  # both rows kept — dedup is a caller decision, not silent drop


def test_full_fixture_end_to_end():
    items, report = analyze.parse_sf_pipeline_csv(FULL_CSV)
    assert report["total_rows"] == 8
    assert report["unmapped_owners"] == ["New Hire Test"], report
    assert report["unmapped_regions"] == ["Atlantis"], report
    assert len(report["duplicate_sfids"]) == 1, report


def test_reused_functions_still_work_unchanged():
    """The real regression-proof: feed SF-normalized items straight into the existing
    pure aggregation functions and confirm no exceptions, sane shape."""
    items, _ = analyze.parse_sf_pipeline_csv(FULL_CSV)
    p = analyze.pipeline(items, "2026-08-17")
    assert "open_count" in p and "open_acv" in p and "by_stage" in p
    sc = analyze.scorecard(items, "2026-08-17")
    assert sc["overall"]["total"] == 8
    wr = analyze.winrate(items, "2026-01-01", "2026-12-31")
    assert "strict" in wr and "sensitivity" in wr
    sbs = analyze.se_by_stage(items)
    assert "Diego Cione" in [r["owner"] for r in sbs["rows"]]
    hyg = analyze.hygiene_by_owner(items)
    assert "Diego Cione" in hyg


def test_orphan_rocketlane_projects_flags_unmatched_sfid():
    sf_items, _ = analyze.parse_sf_pipeline_csv(HEADER + "\n" + REDSEA + "\n")
    sf_sfids = {analyze.norm_sfid(r["sfid"]) for _, r in sf_items}
    rl_items = [
        ("1210507", {"name": "RedSea Global Saudi B2B Marketplace", "owner": "Diego Cione",
                     "stage": "Commit & Signing", "acv": 431666.67, "macro": "EMEA-APAC",
                     "sfid": "006U600000ZFcGzIAL"}),  # matches -> not an orphan
        ("1360870", {"name": "Rubis Energy Kenya", "owner": "Diego Cione",
                     "stage": "Qualification", "acv": 20000000, "macro": "EMEA-APAC",
                     "sfid": "006NOMATCHXXXXX"}),  # no match -> orphan, the real case
    ]
    orphans = analyze.orphan_rocketlane_projects(rl_items, sf_sfids)
    names = [o["name"] for o in orphans]
    assert "Rubis Energy Kenya" in names, orphans
    assert "RedSea Global Saudi B2B Marketplace" not in names, orphans
    assert orphans[0]["acv"] == 20000000, orphans  # sorted by ACV desc


ALL_TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

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
