#!/usr/bin/env python3
"""
Pure analysis functions over a raw Rocketlane project list.

No I/O, no network — takes the `projects` list (as returned by rl_api.pull_projects)
and returns JSON-serializable results. Ported from scratchpad/winrate/analyze_final.py
(validated 2026-07-07: SE H1 2026 = 7 Won / 10 Lost = 41.2% strict / 46.9% sensitivity).

Kept dependency-free and side-effect-free so the SAME functions can back both the
`rocketlane` skill and (later) high-level tools in Wagner's MCP server.
"""
from __future__ import annotations

import datetime as _dt
import re
from collections import defaultdict
from typing import Any

# SE-team discriminator — decision 2026-07-07: Template SE only, ignore "Template SE - B2B".
SE_TEMPLATE_IDS = {"520608"}

# Canonical Opportunity Stage order (for SE×Stage matrices / column ordering).
STAGE_ORDER = ["Qualification", "Scope & Validate", "Active Pursuit", "Proposal",
               "Negotiate", "Commit & Signing", "Won", "Lost"]

# Macro Region normalization (free-text field, account-specific). Single source of truth.
_MACRO_REGION_MAP = {"United States": "USA", "EMEA - APAC": "EMEA-APAC"}

STAGE_ORDER = ["Qualification", "Active Pursuit", "Scope & Validate", "Proposal",
               "Negotiate", "Commit & Signing", "Won", "Lost"]


def normalize_macro_region(r: str | None) -> str:
    if not r:
        return "(no region)"
    r = r.strip()
    return _MACRO_REGION_MAP.get(r, r)


def _flatten_fields(p: dict) -> dict:
    out = {}
    for f in p.get("fields", []) or []:
        label = f.get("fieldLabel")
        val = f.get("fieldValueLabel")
        if val is None:
            val = f.get("fieldValue")
        out[label] = val
    return out


def project_row(p: dict) -> dict:
    fl = _flatten_fields(p)
    src = (p.get("sources") or [{}])[0]
    owner = p.get("owner") or {}
    owner_name = (f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip()
                  or owner.get("emailId") or "(sem owner)")
    creator = p.get("createdBy") or {}
    creator_name = (f"{creator.get('firstName', '')} {creator.get('lastName', '')}".strip()
                    or creator.get("emailId") or "")
    return {
        "name": p.get("projectName", "?"),
        "archived": bool(p.get("archived")),
        "stage": fl.get("Opportunity Stage") or "",
        "closed": str(fl.get("Opp Closed Date") or ""),
        "acv": fl.get("ACV"),
        "sfid": str(fl.get("Opportunity ID") or ""),
        "loss": str(fl.get("Backlog Loss reason") or ""),
        "cancel": str(fl.get("Cancellation Reason") or ""),
        "region": str(fl.get("Sales Region") or ""),
        "macro": normalize_macro_region(fl.get("Macro Region")),
        "tpl": str(src.get("templateId") or ""),
        "tplname": src.get("templateName") or "",
        "status": (p.get("status") or {}).get("label", ""),
        "owner": owner_name,
        "owner_email": owner.get("emailId", ""),
        "created_by": creator_name,
        "gmv": fl.get("Estimated GMV"),
        "team_emails": [m.get("emailId") for m in ((p.get("teamMembers") or {}).get("members") or [])
                        if m.get("emailId")],
        "created_ms": p.get("createdAt"),
        "updatedAt": p.get("updatedAt"),
    }


def rows_from_projects(projects: list[dict]) -> dict[str, dict]:
    return {str(p["projectId"]): project_row(p) for p in projects}


def _is_dead_sync_artifact(r: dict) -> bool:
    """Validated 2026-07-14: a Rocketlane record auto-created by the Salesforce sync that was
    never staged (batch-created, no ACV, never worked by a human) — as opposed to a real SE
    opportunity that just hasn't been staged yet (which the SE themselves created — see
    'created_by'). Safe to exclude: since Won/Lost require a stage, this can NEVER remove a
    Won/Lost outcome; all 94 known instances have ACV 0/None, so it can't drop $ either.
    Zero impact on any per-region digest (all instances fall in the '(no region)' bucket)."""
    return r["created_by"] == "Salesforce" and not r["stage"]


def scope_se(rows: dict[str, dict]) -> list[tuple[str, dict]]:
    return [(pid, r) for pid, r in rows.items()
            if r["tpl"] in SE_TEMPLATE_IDS and not _is_dead_sync_artifact(r)]


def norm_sfid(raw: str) -> str:
    m = re.search(r"(006[a-zA-Z0-9]{12,15})", raw or "")
    return m.group(1)[:15] if m else ""


def acvn(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def in_window(d: str, start: str, end: str) -> bool:
    return bool(d) and start <= d <= end


def dedupe(items: list[tuple[str, dict]]) -> tuple[list[tuple[str, dict]], list]:
    groups = defaultdict(list)
    for pid, r in items:
        key = norm_sfid(r["sfid"]) or f"__{pid}"
        groups[key].append((pid, r))
    out, conflicts = [], []
    for key, ms in groups.items():
        ms.sort(key=lambda m: (m[1]["archived"], -int(m[0])))
        out.append(ms[0])
        if len({m[1]["stage"] for m in ms}) > 1:
            conflicts.append({"key": key, "members": [
                {"pid": p, "name": r["name"], "stage": r["stage"], "archived": r["archived"]}
                for p, r in ms]})
    return out, conflicts


def current_half(today: str) -> tuple[str, str]:
    """today = 'YYYY-MM-DD' → (start, end) of the current calendar half."""
    year, month = today[:4], int(today[5:7])
    return (f"{year}-01-01", f"{year}-06-30") if month <= 6 else (f"{year}-07-01", f"{year}-12-31")


def winrate(items: list[tuple[str, dict]], start: str, end: str, top_n: int = 10) -> dict[str, Any]:
    """items already scoped (e.g. Template SE). Stage-first, then date window (Trap 5)."""
    opps_raw = [(p, r) for p, r in items if r["stage"]]
    opps, conflicts = dedupe(opps_raw)
    wh = [(p, r) for p, r in opps if r["stage"] == "Won" and in_window(r["closed"], start, end)]
    lh = [(p, r) for p, r in opps if r["stage"] == "Lost" and in_window(r["closed"], start, end)]
    wa = [(p, r) for p, r in opps if r["stage"] == "Won"]
    la = [(p, r) for p, r in opps if r["stage"] == "Lost"]
    wnd = [x for x in wa if not x[1]["closed"]]
    lnd = [x for x in la if not x[1]["closed"]]
    openn = [(p, r) for p, r in opps if r["stage"] not in ("Won", "Lost")]
    strict = len(wh) / max(1, len(wh) + len(lh))
    sens = (len(wh) + len(wnd)) / max(1, len(wh) + len(wnd) + len(lh) + len(lnd))

    def srt(lst):
        wv = sorted([x for x in lst if acvn(x[1]["acv"]) is not None], key=lambda x: -acvn(x[1]["acv"]))
        return wv + [x for x in lst if acvn(x[1]["acv"]) is None]

    top_lost = [{
        "projectId": p, "name": r["name"], "acv": acvn(r["acv"]),
        "closed": r["closed"], "macro": r["macro"], "region": r["region"],
        "archived": r["archived"], "owner": r["owner"],
        "reason": r["loss"] or r["cancel"] or None,
    } for p, r in srt(lh)[:top_n]]

    return {
        "window": {"from": start, "to": end},
        "won": len(wh), "lost": len(lh),
        "strict": round(strict, 4), "sensitivity": round(sens, 4),
        "won_no_date": len(wnd), "lost_no_date": len(lnd),
        "won_total": len(wa), "lost_total": len(la), "open": len(openn),
        "loss_reason_fill": {"backlog": sum(1 for _, r in la if r["loss"]),
                             "cancellation": sum(1 for _, r in la if r["cancel"]),
                             "of_lost": len(la)},
        "top_lost": top_lost,
        "dedupe_conflicts": conflicts[:10],
        "unique_after_dedupe": len(opps), "twins_collapsed": len(opps_raw) - len(opps),
    }


def _matrix(items: list[tuple[str, dict]], keyf) -> dict[str, Any]:
    staged = [(p, r) for p, r in items if r["stage"]]
    stages = [s for s in STAGE_ORDER if s in {r["stage"] for _, r in staged}]
    cells = defaultdict(lambda: defaultdict(lambda: [0, 0.0]))
    for p, r in staged:
        c = cells[keyf(r)][r["stage"]]
        c[0] += 1
        c[1] += acvn(r["acv"]) or 0.0
    matrix = {}
    for k in cells:
        matrix[k] = {s: {"count": cells[k][s][0], "acv": round(cells[k][s][1])}
                     for s in stages if cells[k][s][0]}
    return {"stages": stages, "rows": matrix}


def report(items: list[tuple[str, dict]]) -> dict[str, Any]:
    return {
        "se_x_stage": _matrix(items, lambda r: r["owner"]),
        "macro_region_x_stage": _matrix(items, lambda r: r["macro"]),
        "total": len(items),
        "staged": sum(1 for _, r in items if r["stage"]),
    }


def health(items: list[tuple[str, dict]]) -> dict[str, Any]:
    no_stage = [(p, r) for p, r in items if not r["stage"]]
    sf_owned = [(p, r) for p, r in items if r["owner"].lower().startswith("salesforce")]
    closed_missing_date = [(p, r) for p, r in items
                           if r["stage"] in ("Won", "Lost") and not r["closed"]]
    acv_zero = [(p, r) for p, r in items if r["stage"] and (acvn(r["acv"]) or 0) == 0]
    _, conflicts = dedupe([(p, r) for p, r in items if r["stage"]])
    by_owner = defaultdict(int)
    for _, r in no_stage:
        by_owner[r["owner"]] += 1
    return {
        "total": len(items),
        "no_stage": len(no_stage),
        "no_stage_by_owner": dict(sorted(by_owner.items(), key=lambda x: -x[1])),
        "salesforce_owned": len(sf_owned),
        "closed_missing_date": len(closed_missing_date),
        "acv_zero_or_missing": len(acv_zero),
        "dedupe_conflicts": len(conflicts),
    }


def diff_snapshots(old: dict[str, dict], new: dict[str, dict]) -> list[dict]:
    """Snapshot diff mirroring the RL webhook changeLog shape {changedFields, from, to}.
    A future real PROJECT_UPDATED feed plugs into the same alert consumers unchanged."""
    watched = ["stage", "closed", "owner", "acv", "archived", "status"]
    alerts = []
    for pid, nr in new.items():
        if pid not in old:
            alerts.append({"projectId": pid, "name": nr["name"], "eventType": "PROJECT_CREATED",
                           "resourceType": "PROJECT",
                           "note": "new opp" + ("" if nr["stage"] else " (no stage)")})
            continue
        orow = old[pid]
        changed = {f: {"from": orow.get(f), "to": nr.get(f)} for f in watched if orow.get(f) != nr.get(f)}
        if changed:
            evt = {"projectId": pid, "name": nr["name"], "eventType": "PROJECT_UPDATED",
                   "resourceType": "PROJECT", "changedFields": list(changed.keys()),
                   "from": {f: changed[f]["from"] for f in changed},
                   "to": {f: changed[f]["to"] for f in changed}}
            if "stage" in changed and nr["stage"] in ("Won", "Lost"):
                evt["note"] = f"→ {nr['stage']}"
            alerts.append(evt)
    return alerts


# ===========================================================================
# Report catalog — coverage helper, owner-remap, primitives, audience digests
# Every metric carries a coverage block {value, n, of, coverage, as_of}.
# ACV is the reliable $ measure; GMV is dirty (outliers) — exec views only.
# ===========================================================================

def covered(value, n, total, as_of=None):
    return {"value": value, "n": n, "of": total,
            "coverage": round(n / total, 3) if total else None, "as_of": as_of}


def _is_open(r):
    return bool(r["stage"]) and r["stage"] not in ("Won", "Lost")


def _d(s):
    """'YYYY-MM-DD' -> date, or None. Pure (no wall-clock)."""
    try:
        return _dt.date.fromisoformat(str(s)[:10])
    except (TypeError, ValueError):
        return None


def _days_between(d1, d2):
    """Whole days from d1 to d2 (both 'YYYY-MM-DD'); None if unparseable."""
    a, b = _d(d1), _d(d2)
    return (b - a).days if a and b else None


def _status_open(r):
    """Project not administratively closed (Completed/Cancelled)."""
    return r["status"] not in ("Completed", "Cancelled")


_SEV_ORDER = {"red": 0, "yellow": 1, "green": 2}
_SEV_EMOJI = {"red": "🔴", "yellow": "🟡", "green": "🟢"}


def opp_health(r, today, soon_days=14):
    """Deterministic 🟢/🟡/🔴 + risk flags for ONE opportunity (a governance-review row).
    Only computable-reliable signals — no updatedAt (bot-polluted), no invented scores."""
    flags = []
    is_open = _is_open(r)
    if is_open and r["closed"] and r["closed"] < today:                 # 🔴 past forecast close, still open
        n = _days_between(r["closed"], today)
        flags.append(("red", f"overdue {n}d" if n is not None else "close date overdue"))
    if r["stage"] in ("Won", "Lost") and _status_open(r):               # 🔴 Won/Lost but not closed out
        flags.append(("red", f"{r['stage']} but still open"))
    if not r["stage"]:                                                  # 🟡 unclassified
        flags.append(("yellow", "no stage"))
    if r["stage"] and acvn(r["acv"]) is None:                           # 🟡 staged but no ACV
        flags.append(("yellow", "no ACV"))
    if is_open and r["closed"] and today <= r["closed"]:                # 🟡 approaching forecast close
        n = _days_between(today, r["closed"])
        if n is not None and n <= soon_days:
            flags.append(("yellow", f"closing in {n}d"))
    sev = "red" if any(f[0] == "red" for f in flags) else ("yellow" if flags else "green")
    return {"health": _SEV_EMOJI[sev], "severity": sev, "flags": [f[1] for f in flags]}


def opps_detail(items, today):
    """Per-opportunity governance rows (health + flags), 🔴 first then by ACV desc.
    Serves the 'governance review per opp' need SERVER-SIDE — the copilot renders the
    table from this and never falls back to the (silently broken) owner filter."""
    rows = []
    for p, r in items:
        rows.append({"projectId": p, "name": r["name"],
                     "stage": r["stage"] or "(no stage)", "owner": r["owner"],
                     "acv": acvn(r["acv"]), "closed_forecast": r["closed"],
                     "status": r["status"], **opp_health(r, today)})
    rows.sort(key=lambda x: (_SEV_ORDER[x["severity"]], -(x["acv"] or 0)))
    return rows


def _first_human_member(p):
    for m in ((p.get("teamMembers") or {}).get("members") or []):
        nm = (f"{m.get('firstName', '')} {m.get('lastName', '')}".strip() or m.get("emailId") or "")
        if nm and not nm.lower().startswith("salesforce"):
            return {"name": nm, "email": m.get("emailId")}
    return None


def remap_owners(projects):
    """Salesforce-owned SE opps with a human owner inferred from teamMembers.
    Prerequisite for any per-SE report."""
    out = []
    for p in projects:
        if str(((p.get("sources") or [{}])[0]).get("templateId") or "") not in SE_TEMPLATE_IDS:
            continue
        owner = p.get("owner") or {}
        onm = (f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip() or owner.get("emailId") or "")
        if onm.lower().startswith("salesforce"):
            fl = _flatten_fields(p)
            inferred = _first_human_member(p)
            out.append({"projectId": str(p["projectId"]), "name": p.get("projectName"),
                        "stage": fl.get("Opportunity Stage") or "", "acv": acvn(fl.get("ACV")),
                        "inferred_owner": inferred,
                        "team_size": len((p.get("teamMembers") or {}).get("members") or [])})
    return {"total_salesforce_owned": len(out),
            "with_inferred_human": sum(1 for x in out if x["inferred_owner"]),
            "no_team_to_infer": sum(1 for x in out if not x["inferred_owner"]), "opps": out}


def pipeline(items, as_of=None):
    """Open pipeline (stage set, not Won/Lost) by stage: count + ACV + GMV."""
    total = len(items)
    op = [(p, r) for p, r in items if _is_open(r)]
    by_stage = defaultdict(lambda: {"count": 0, "acv": 0.0, "gmv": 0.0})
    for _, r in op:
        c = by_stage[r["stage"]]
        c["count"] += 1
        c["acv"] += acvn(r["acv"]) or 0.0
        c["gmv"] += acvn(r["gmv"]) or 0.0
    for s in by_stage:
        by_stage[s]["acv"] = round(by_stage[s]["acv"])
        by_stage[s]["gmv"] = round(by_stage[s]["gmv"])
    return {"open_count": len(op),
            "open_acv": round(sum(acvn(r["acv"]) or 0 for _, r in op)),
            "by_stage": dict(by_stage),
            "_coverage": covered("open pipeline", len(op), total, as_of)}


def scorecard(items, as_of=None):
    """Data-quality by Macro Region — the governance KPI."""
    def block(subset):
        n = len(subset)
        if not n:
            return None
        staged = sum(1 for _, r in subset if r["stage"])
        sf = sum(1 for _, r in subset if r["owner"].lower().startswith("salesforce"))
        closed = [(p, r) for p, r in subset if r["stage"] in ("Won", "Lost")]
        miss_close = sum(1 for _, r in closed if not r["closed"])
        miss_acv = sum(1 for _, r in subset if r["stage"] and acvn(r["acv"]) is None)
        miss_region = sum(1 for _, r in subset if r["macro"] == "(no region)")
        return {"total": n, "pct_staged": round(staged / n, 3),
                "pct_salesforce_owned": round(sf / n, 3),
                "pct_closed_missing_date": round(miss_close / len(closed), 3) if closed else None,
                "pct_staged_missing_acv": round(miss_acv / max(1, staged), 3),
                "pct_missing_region": round(miss_region / n, 3)}
    by_region = {}
    for reg in sorted({r["macro"] for _, r in items}):
        b = block([(p, r) for p, r in items if r["macro"] == reg])
        if b:
            by_region[reg] = b
    return {"as_of": as_of, "overall": block(items), "by_region": by_region}


def overdue(items, today):
    """At-risk WITHOUT proxy: Opp Closed Date in the past but stage still open."""
    out = [{"projectId": p, "name": r["name"], "stage": r["stage"], "acv": acvn(r["acv"]),
            "closed_forecast": r["closed"], "macro": r["macro"], "owner": r["owner"]}
           for p, r in items if _is_open(r) and r["closed"] and r["closed"] < today]
    out.sort(key=lambda x: x["closed_forecast"])
    return {"count": len(out), "opps": out}


def hygiene_by_owner(items):
    """Data completeness per owner — positive-framed hygiene leaderboard."""
    by = defaultdict(lambda: {"total": 0, "missing_stage": 0, "missing_acv": 0})
    for _, r in items:
        b = by[r["owner"]]
        b["total"] += 1
        if not r["stage"]:
            b["missing_stage"] += 1
        if acvn(r["acv"]) is None:
            b["missing_acv"] += 1
    for o in by:
        t = by[o]["total"]
        by[o]["completeness"] = round(1 - by[o]["missing_stage"] / t, 3) if t else None
    return dict(sorted(by.items(), key=lambda x: -x[1]["total"]))


def _my_items(items, email):
    e = (email or "").lower()
    return [(p, r) for p, r in items
            if r["owner_email"].lower() == e or e in [x.lower() for x in r["team_emails"]]]


def se_by_stage(items):
    """Opportunity count per SE (owner) × stage — the region leader's 'opps per SE by stage'.
    Rows alphabetical by owner (a workload view, NOT a performance ranking). '(no stage)'
    is an explicit last column, never hidden."""
    by_owner: dict[str, dict] = {}
    present: set[str] = set()
    for _, r in items:
        owner = r["owner"] or "(no owner)"
        stage = r["stage"] or "(no stage)"
        by_owner.setdefault(owner, {})
        by_owner[owner][stage] = by_owner[owner].get(stage, 0) + 1
        present.add(stage)
    cols = [s for s in STAGE_ORDER if s in present]
    for s in sorted(present):  # any non-canonical stage, defensively, before (no stage)
        if s not in cols and s != "(no stage)":
            cols.append(s)
    if "(no stage)" in present:
        cols.append("(no stage)")
    rows = [{"owner": o, "counts": {c: by_owner[o].get(c, 0) for c in cols},
             "total": sum(by_owner[o].values())} for o in sorted(by_owner)]
    return {"columns": cols, "rows": rows, "total": sum(r["total"] for r in rows)}


def top_opps(items, today, n=5):
    """Top-N opportunities by ACV, each carrying its health status (🔴/🟡/🟢), plus a
    status-count summary — the region leader's 'top 5 opps categorized by status'."""
    scored = []
    summary = {"red": 0, "yellow": 0, "green": 0}
    for p, r in items:
        h = opp_health(r, today)
        summary[h["severity"]] = summary.get(h["severity"], 0) + 1
        scored.append({"projectId": p, "name": r["name"], "stage": r["stage"] or "(no stage)",
                       "owner": r["owner"], "acv": acvn(r["acv"]), "closed_forecast": r["closed"], **h})
    top = sorted(scored, key=lambda x: -(x["acv"] or 0))[:n]
    return {"summary": summary, "top": top}


def se_digest(items, email, today):
    mine = _my_items(items, email)
    total = len(mine)
    nudges = {
        "no_stage": [{"projectId": p, "name": r["name"], "acv": acvn(r["acv"])} for p, r in mine if not r["stage"]],
        "no_close_date": [{"projectId": p, "name": r["name"]} for p, r in mine if r["stage"] in ("Won", "Lost") and not r["closed"]],
        "no_acv": [{"projectId": p, "name": r["name"]} for p, r in mine if r["stage"] and acvn(r["acv"]) is None],
    }
    return {"se": email, "my_opps": total,
            "hygiene_nudges": {k: {"count": len(v), "opps": v} for k, v in nudges.items()},
            "my_pipeline": pipeline(mine, today),
            "at_risk_overdue": overdue(mine, today),
            "my_opps_detail": opps_detail(mine, today),
            "_coverage": covered("my opps", total, total, today)}


def _stage_idx(s):
    try:
        return STAGE_ORDER.index(s)
    except ValueError:
        return -1


def week_movement(old, new, today, since=None):
    """Week-over-week highlight/lowlight from two {pid: row} snapshots. DETERMINISTIC and
    STRUCTURED (kind/opp/acv/from/to — the template formats the sentence; never LLM prose).
    highlight: Won > stage advance > big new opp. lowlight: Lost > slipped past close > regress."""
    if not old:
        return {"status": "insufficient_history", "highlights": [], "lowlights": [], "since": since}
    highs, lows = [], []
    for pid, r in new.items():
        o = old.get(pid)
        acv = acvn(r["acv"]) or 0
        ns, os_ = r["stage"], (o["stage"] if o else "")
        if ns == "Won" and (not o or os_ != "Won"):
            highs.append({"kind": "won", "opp": r["name"], "acv": acv})
        elif ns == "Lost" and (not o or os_ != "Lost"):
            lows.append({"kind": "lost", "opp": r["name"], "acv": acv})
        elif o and os_ and ns and os_ != ns and ns not in ("Won", "Lost") and os_ not in ("Won", "Lost"):
            if _stage_idx(ns) > _stage_idx(os_):
                highs.append({"kind": "advance", "opp": r["name"], "acv": acv, "from": os_, "to": ns})
            elif _stage_idx(ns) < _stage_idx(os_):
                lows.append({"kind": "regress", "opp": r["name"], "acv": acv, "from": os_, "to": ns})
        if not o and ns not in ("Won", "Lost"):
            highs.append({"kind": "new", "opp": r["name"], "acv": acv})
        if o and _is_open(r) and r["closed"] and r["closed"] < today and (not o["closed"] or o["closed"] >= today):
            lows.append({"kind": "slipped", "opp": r["name"], "acv": acv})
    hr = {"won": 0, "advance": 1, "new": 2}
    lr = {"lost": 0, "slipped": 1, "regress": 2}
    highs.sort(key=lambda x: (hr.get(x["kind"], 9), -(x["acv"] or 0)))
    lows.sort(key=lambda x: (lr.get(x["kind"], 9), -(x["acv"] or 0)))
    return {"status": "ok", "highlights": highs[:2], "lowlights": lows[:2], "since": since}


def _movement(cur_items, prev_items, today):
    if prev_items is None:
        return {"status": "insufficient_history", "highlights": [], "lowlights": []}
    return week_movement({p: r for p, r in prev_items}, {p: r for p, r in cur_items}, today)


def region_digest(items, macro, today, prev_items=None):
    reg = [(p, r) for p, r in items if r["macro"] == macro]
    total = len(reg)
    prev_reg = ([(p, r) for p, r in prev_items if r["macro"] == macro]
                if prev_items is not None else None)
    return {"region": macro, "opps": total,
            "funnel": pipeline(reg, today),
            "se_by_stage": se_by_stage(reg),
            "top_opps": top_opps(reg, today),
            "hygiene_by_se": hygiene_by_owner(reg),
            "at_risk_overdue": overdue(reg, today),
            "no_stage": sum(1 for _, r in reg if not r["stage"]),
            "movement": _movement(reg, prev_reg, today),
            "_coverage": covered("region opps", total, total, today)}


def half_windows(today, n=4):
    """Last n calendar-half windows, newest first: [(label, start, end), ...]."""
    yy, hh = int(today[:4]), (1 if int(today[5:7]) <= 6 else 2)
    out = []
    for _ in range(n):
        if hh == 1:
            out.append((f"H1 {yy}", f"{yy}-01-01", f"{yy}-06-30"))
            yy, hh = yy - 1, 2
        else:
            out.append((f"H2 {yy}", f"{yy}-07-01", f"{yy}-12-31"))
            hh = 1
    return out


def exec_digest(items, today, start=None, end=None, prev_items=None):
    # Win-rate: a trend across recent halves (a single "current half" is near-empty
    # early in a half — the VP wants the trajectory). Custom window if given.
    if start and end:
        wr_trend = {"custom": winrate(items, start, end)}
    else:
        wr_trend = {label: winrate(items, s, e) for label, s, e in half_windows(today, 4)}
    return {"as_of": today,
            "data_quality_scorecard": scorecard(items, today),
            "org_winrate_trend": wr_trend,
            "movement": _movement(items, prev_items, today),
            "pipeline_region_stage": {reg: pipeline([(p, r) for p, r in items if r["macro"] == reg], today)
                                      for reg in sorted({r["macro"] for _, r in items})}}
