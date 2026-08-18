#!/usr/bin/env python3
"""Dependency-free assert-based tests for phase inference (se_by_phase).
Run: python3 python/tests/test_se_by_phase.py
No pytest — this repo has zero test infra and zero non-stdlib deps; keep it that way.
Fixtures captured live 2026-08-12 against project ids 1209846/1210507/1209847/1319038
(Diego Cione's book), trimmed to the fields infer_phase actually reads.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import analyze


def _t(name, status_value, status_label):
    return {"taskName": name, "status": {"value": status_value, "label": status_label}}


# Project 1209846 "Ethara B2C/B2B Formula 1 Merchandise" — everything untouched.
FIXTURE_1209846 = [
    _t("Discovery Meeting", 1, "To do"), _t("Opportunity Folder created", 1, "To do"),
    _t("Discovery Document", 1, "To do"), _t("RFP", 1, "To do"), _t("Demo", 1, "To do"),
    _t("Any specific requirement covered", 1, "To do"), _t("POC", 1, "To do"),
    _t("Solution Design Document", 1, "To do"), _t("Architecture", 1, "To do"),
    _t("PS proposal request", 1, "To do"), _t("Knowledge Transfer Document to PS", 1, "To do"),
    _t("Handover to PS", 1, "To do"),
]

# Project 1210507 "RedSea Global Saudi B2B Marketplace" — the ticket's own bug fixture:
# 3 simultaneous in-progress tasks (idx6, idx7, idx9). "Discovery Document" never created.
FIXTURE_1210507 = [
    _t("Discovery Meeting", 3, "Completed"), _t("Opportunity Folder created", 3, "Completed"),
    _t("RFP", 3, "Completed"), _t("Demo", 3, "Completed"),
    _t("Any specific requirement covered", 3, "Completed"), _t("POC", 3, "Completed"),
    _t("Solution Design Document", 2, "In progress"), _t("Architecture", 2, "In progress"),
    _t("PS proposal request", 3, "Completed"),
    _t("Knowledge Transfer Document to PS", 2, "In progress"),
    _t("Handover to PS", 1, "To do"),
    _t("Meeting with CTO", 3, "Completed"), _t("V1 of Solution design to Red sea", 3, "Completed"),
]

# Project 1209847 "B2C Abela Supermarket" — Demo/POC done, Discovery Document/RFP still To do
# (out-of-sequence completion -> stale=True).
FIXTURE_1209847 = [
    _t("Discovery Meeting", 3, "Completed"), _t("Opportunity Folder created", 1, "To do"),
    _t("Discovery Document", 1, "To do"), _t("RFP", 1, "To do"), _t("Demo", 3, "Completed"),
    _t("Any specific requirement covered", 3, "Completed"), _t("POC", 3, "Completed"),
    _t("Solution Design Document", 1, "To do"), _t("Architecture", 1, "To do"),
    _t("PS proposal request", 1, "To do"), _t("Knowledge Transfer Document to PS", 1, "To do"),
    _t("Handover to PS", 1, "To do"),
]

# Project 1319038 "G2A Poland" — custom tasks (RFI/NDA/Discovery Questions/Proposal Sent) must
# not shift phase. "RFP" never created (replaced by custom tasks).
FIXTURE_1319038 = [
    _t("Discovery Meeting", 3, "Completed"), _t("Opportunity Folder created", 3, "Completed"),
    _t("Discovery Document", 3, "Completed"), _t("Demo", 3, "Completed"),
    _t("Any specific requirement covered", 1, "To do"), _t("POC", 1, "To do"),
    _t("Solution Design Document", 1, "To do"), _t("Architecture", 1, "To do"),
    _t("PS proposal request", 1, "To do"), _t("Knowledge Transfer Document to PS", 1, "To do"),
    _t("Handover to PS", 1, "To do"),
    _t("RFI", 3, "Completed"), _t("NDA", 3, "Completed"), _t("Discovery Questions", 3, "Completed"),
    _t("Discovery Questions meeting", 3, "Completed"), _t("Proposal Sent", 3, "Completed"),
]

# Project 1209851 "BAS - B2C Super App" — captured live 2026-08-12 from EMEA-APAC. Regression
# fixture: status value 5 ("on hold") is not in the original 4-value spec (1/2/3/4) and crashed
# infer_phase with "max() iterable argument is empty" before the fix (on-hold tasks fell into
# neither the active(2,4) nor completed(3) branch, leaving nothing for the else-branch max()).
FIXTURE_1209851_ON_HOLD = [
    _t("Discovery Meeting", 5, "on hold"), _t("Opportunity Folder created", 2, "In progress"),
    _t("Discovery Document", 5, "on hold"), _t("RFP", 1, "To do"), _t("Demo", 1, "To do"),
    _t("Any specific requirement covered", 1, "To do"), _t("POC", 1, "To do"),
    _t("Solution Design Document", 1, "To do"), _t("Architecture", 1, "To do"),
    _t("PS proposal request", 1, "To do"), _t("Knowledge Transfer Document to PS", 1, "To do"),
    _t("Handover to PS", 1, "To do"),
]


def test_1209846_no_activity():
    r = analyze.infer_phase(FIXTURE_1209846)
    assert r == {"phase": "Discovery Meeting", "bucket": "Discovery Meeting",
                 "stale": False, "no_task_activity": True, "no_playbook_tasks": False}, r


def test_1210507_redsea_min_not_max():
    """The ticket's own pseudocode bug: must pick idx6 (earliest in-progress), not idx9
    (furthest-along) -- confirmed with the user."""
    r = analyze.infer_phase(FIXTURE_1210507)
    assert r["phase"] == "Solution Design Document" and r["bucket"] == "Solution Design", r
    assert r["stale"] is False and r["no_task_activity"] is False, r


def test_1209847_abela_stale_out_of_sequence():
    r = analyze.infer_phase(FIXTURE_1209847)
    assert r["phase"] == "Solution Design Document" and r["bucket"] == "Solution Design", r
    assert r["stale"] is True and r["no_task_activity"] is False, r


def test_1319038_g2a_custom_tasks_and_absent_task_ignored():
    r = analyze.infer_phase(FIXTURE_1319038)
    assert r["phase"] == "Any specific requirement covered" and r["bucket"] == "Demo", r
    assert r["stale"] is False and r["no_task_activity"] is False, r


def test_1209851_on_hold_status_does_not_crash():
    """Regression: status value 5 ('on hold') must not crash infer_phase, and should be
    treated as an active/stalled state (same bucket as In progress/Blocked)."""
    r = analyze.infer_phase(FIXTURE_1209851_ON_HOLD)
    assert r["phase"] == "Discovery Meeting" and r["bucket"] == "Discovery Meeting", r
    assert r["stale"] is False and r["no_task_activity"] is False, r


def test_se_by_phase_fixed_columns_when_empty():
    out = analyze.se_by_phase([], {})
    assert out["columns"] == analyze.SE_BY_PHASE_COLUMNS and out["rows"] == [] and out["total"] == 0
    assert "caveat" in out


def test_se_by_phase_aggregates_and_handles_missing_project():
    items = [("1209846", {"owner": "Diego Cione", "macro": "EMEA-APAC", "status": "In progress"}),
             ("1210507", {"owner": "Diego Cione", "macro": "EMEA-APAC", "status": "In progress"}),
             ("9999999", {"owner": "Diego Cione", "macro": "EMEA-APAC", "status": "In progress"})]  # failed fetch
    tasks_by_project = {"1209846": FIXTURE_1209846, "1210507": FIXTURE_1210507}
    out = analyze.se_by_phase(items, tasks_by_project)
    row = out["rows"][0]
    assert row["owner"] == "Diego Cione"
    assert row["counts"]["Discovery Meeting"] == 1 and row["counts"]["Solution Design"] == 1
    assert row["counts"]["Unknown"] == 1  # the missing project id
    assert row["no_task_activity_count"] == 1 and row["stale_count"] == 0
    assert row["total"] == 3
    assert row["regions"] == ["EMEA-APAC"]


def test_se_by_phase_tags_multiple_regions_per_se():
    """Org-wide (exec) use case: an SE with projects in more than one macro region
    should get every region they touch, sorted, not just the first one seen."""
    items = [("1209846", {"owner": "Diego Cione", "macro": "EMEA-APAC", "status": "In progress"}),
             ("2000001", {"owner": "Diego Cione", "macro": "Brazil", "status": "In progress"})]
    out = analyze.se_by_phase(items, {"1209846": FIXTURE_1209846})
    row = out["rows"][0]
    assert row["regions"] == ["Brazil", "EMEA-APAC"]


def test_se_by_phase_non_active_status_bypasses_phase_entirely():
    """The point of this session's fix: Backlog/On Hold/Stand By/Completed/Closed/
    Cancelled projects must NOT go through infer_phase at all — they're counted by
    their own project status, even if we hand them tasks that would otherwise resolve
    to a real phase. Rocketlane's own status field is the single source of truth here,
    Salesforce never enters into it."""
    items = [
        ("1", {"owner": "Ana", "macro": "Brazil", "status": "Backlog"}),
        ("2", {"owner": "Ana", "macro": "Brazil", "status": "On Hold"}),
        ("3", {"owner": "Ana", "macro": "Brazil", "status": "Stand By"}),
        ("4", {"owner": "Ana", "macro": "Brazil", "status": "Completed"}),
        ("5", {"owner": "Ana", "macro": "Brazil", "status": "Closed"}),
        ("6", {"owner": "Ana", "macro": "Brazil", "status": "Cancelled"}),
    ]
    # every one of these HAS a resolvable phase in its tasks — must be ignored anyway.
    tasks_by_project = {pid: FIXTURE_1210507 for pid, _ in items}
    out = analyze.se_by_phase(items, tasks_by_project)
    row = out["rows"][0]
    assert row["counts"]["Backlog"] == 1
    assert row["counts"]["On Hold"] == 2  # Stand By merges into On Hold
    assert "Completed" not in row["counts"]  # excluded column — not currently active
    assert "Cancelled" not in row["counts"]  # excluded column — not currently active
    assert row["counts"]["Solution Design"] == 0  # never inferred — status wasn't In progress
    assert row["stale_count"] == 0 and row["no_task_activity_count"] == 0
    assert row["total"] == 3  # only Backlog(1) + On Hold(2) — Completed/Cancelled excluded entirely


def test_se_by_phase_unrecognized_status_defaults_to_backlog():
    items = [("1", {"owner": "Ana", "macro": "Brazil", "status": "Some New Status"}),
             ("2", {"owner": "Bea", "macro": "Brazil", "status": ""}),
             ("3", {"owner": "Cia", "macro": "Brazil"})]  # missing "status" key entirely
    out = analyze.se_by_phase(items, {})
    by_owner = {r["owner"]: r for r in out["rows"]}
    assert by_owner["Ana"]["counts"]["Backlog"] == 1
    assert by_owner["Bea"]["counts"]["Backlog"] == 1
    assert by_owner["Cia"]["counts"]["Backlog"] == 1


def test_se_by_phase_cancelled_and_completed_excluded_entirely():
    """Completed/Cancelled projects must not appear ANYWHERE in the table: not in a
    column, not in total, and must not pollute stale_count even when their own tasks
    look stale. Table only ever reports currently-active opportunities."""
    items = [("1", {"owner": "Diego Cione", "macro": "EMEA-APAC", "status": "In progress"}),
             ("2", {"owner": "Diego Cione", "macro": "EMEA-APAC", "status": "Cancelled"}),
             ("3", {"owner": "Diego Cione", "macro": "EMEA-APAC", "status": "Completed"})]
    tasks_by_project = {"1": FIXTURE_1209847, "2": FIXTURE_1209847, "3": FIXTURE_1209847}
    out = analyze.se_by_phase(items, tasks_by_project)
    row = out["rows"][0]
    assert row["stale_count"] == 1  # only project "1" (In progress) counts
    assert row["total"] == 1  # Cancelled + Completed fully excluded, not just uncounted
    assert "Completed" not in row["counts"] and "Cancelled" not in row["counts"]


def test_se_by_phase_owner_with_only_closed_out_projects_is_absent():
    """An SE whose entire book is Completed/Cancelled shouldn't appear in rows at all —
    not as a row with all-zero counts, genuinely absent."""
    items = [("1", {"owner": "Retired SE", "macro": "Brazil", "status": "Cancelled"})]
    out = analyze.se_by_phase(items, {})
    assert out["rows"] == [] and out["total"] == 0


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
