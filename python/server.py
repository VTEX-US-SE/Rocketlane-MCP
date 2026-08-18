#!/usr/bin/env python3
"""
Rocketlane MCP server.

Exposes the Rocketlane REST API v1.0 (https://api.rocketlane.com/api/1.0) as
MCP tools so Claude (Cowork, Desktop, Code) can talk to Rocketlane without
relying on the Cowork sandbox network egress allowlist — MCP traffic runs in
this process, outside the sandbox, and goes straight to api.rocketlane.com.

Design mirrors the existing rocketlane-apis skill:
- One generic tool (`rocketlane_request`) covers all 64 endpoints.
- A small set of named convenience tools (list/get projects, tasks, users,
  invoices, phases) for the most common Sales SE reads.
- An auto-paginating helper (`rocketlane_get_all`).

Read-vs-write discipline (confirm before any POST/PUT/PATCH/DELETE) is
enforced by the assistant per project instructions, not by this server.
"""
from __future__ import annotations

import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import certifi
from mcp.server.fastmcp import FastMCP

BASE_URL = "https://api.rocketlane.com/api/1.0"
TIMEOUT_S = 30

# Explicit CA bundle for urllib requests. Needed because some Python installs
# (notably python.org's macOS framework build, when "Install Certificates.command"
# was never run) ship without a working system cert.pem — urllib then fails every
# HTTPS call with CERTIFICATE_VERIFY_FAILED even though certifi (an mcp/httpx
# dependency) is installed and has a valid bundle right there.
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# ---------------------------------------------------------------------------
# Credential resolution
#
# Resolution order:
#   1. $ROCKETLANE_API_KEY env var
#   2. Path in $ROCKETLANE_CREDENTIALS env var
#   3. Sibling skill folder: <this dir>/../rocketlane-apis/credentials.json
#   4. Same dir as this server: <this dir>/credentials.json
#   5. ~/.rocketlane/credentials.json (or plaintext fallback)
#
# Never echo the key. If the key is missing, raise — the MCP tool call will
# return that error to the assistant, which surfaces it to the user.
# ---------------------------------------------------------------------------

_CRED_FILENAMES = ("credentials.json", "credentials")
_CRED_KEY_NAMES = {"api-key", "api_key", "apikey", "rocketlane_api_key"}


def _candidate_credential_paths() -> list[Path]:
    explicit = os.environ.get("ROCKETLANE_CREDENTIALS")
    if explicit:
        return [Path(explicit).expanduser()]

    here = Path(__file__).resolve().parent
    candidates: list[Path] = []
    # 1) sibling skill folder (the existing skill the user already populated)
    skill_dir = here.parent / "rocketlane-apis"
    # 2) same dir as this MCP server
    same_dir = here
    # 3) home
    home_dir = Path.home() / ".rocketlane"

    for d in (skill_dir, same_dir, home_dir):
        for name in _CRED_FILENAMES:
            candidates.append(d / name)
    return candidates


def _read_key_from_file(path: Path) -> str | None:
    try:
        content = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not content:
        return None
    # JSON
    if content.startswith("{"):
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        for key, value in data.items():
            if str(key).lower().replace("_", "-") in {"api-key", "apikey", "rocketlane-api-key"}:
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None
    # plaintext: either bare key or "api-key=..." / "api_key=..."
    if "=" in content:
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip().lower().replace("_", "-") in {"api-key", "apikey", "rocketlane-api-key"}:
                return v.strip().strip('"').strip("'")
        return None
    return content


def _resolve_api_key() -> str:
    env_key = os.environ.get("ROCKETLANE_API_KEY")
    if env_key and env_key.strip():
        return env_key.strip()
    for path in _candidate_credential_paths():
        if path.is_file():
            key = _read_key_from_file(path)
            if key:
                return key
    raise RuntimeError(
        "Rocketlane API key not found. Set $ROCKETLANE_API_KEY, or place "
        "credentials.json with {\"api-key\": \"rl-...\"} in the rocketlane-apis "
        "skill folder, the rocketlane-mcp folder, or ~/.rocketlane/."
    )


# ---------------------------------------------------------------------------
# Slack bot identity (for post_slack_dm) — separate credential, same store
# ---------------------------------------------------------------------------


def _resolve_slack_token() -> str:
    """Slack bot token for the team's app identity ("SE Co-Pilot Agent") — env
    SLACK_BOT_TOKEN first, else the same credentials.json files used for the Rocketlane
    key. Never logged. '' if unset (the tool call surfaces that, not a raise, since Slack
    DMs are optional on top of the core Rocketlane tools)."""
    env_tok = os.environ.get("SLACK_BOT_TOKEN", "").strip()
    if env_tok:
        return env_tok
    for path in _candidate_credential_paths():
        if not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if not content or not content.startswith("{"):
            continue
        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        for key, value in data.items():
            if str(key).lower().replace("_", "-") in {"slack-bot-token", "slack-token", "slack-bot"}:
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return ""


def _slack_lookup_user(email: str, token: str) -> dict[str, Any]:
    """Resolve a Slack user id from an email (needs the users:read.email scope)."""
    url = "https://slack.com/api/users.lookupByEmail?email=" + urllib.parse.quote(email)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=_SSL_CONTEXT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        if body.get("ok"):
            return {"user_id": body["user"]["id"]}
        return {"error": True, "message": "lookup: " + body.get("error", "?")}
    except (urllib.error.URLError, KeyError, ValueError) as e:
        return {"error": True, "message": f"lookup failure: {e}"}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------


def _build_url(path: str, query: dict | None) -> str:
    if not path.startswith("/"):
        path = "/" + path
    url = BASE_URL + path
    if query:
        # Preserve dotted filter keys like "projectName.cn" — urlencode handles
        # this fine. Stringify scalars, drop None values.
        pairs: list[tuple[str, str]] = []
        for k, v in query.items():
            if v is None:
                continue
            if isinstance(v, (list, tuple)):
                for item in v:
                    pairs.append((str(k), str(item)))
            else:
                pairs.append((str(k), str(v)))
        if pairs:
            url += "?" + urllib.parse.urlencode(pairs)
    return url


def _call(
    method: str,
    path: str,
    query: dict | None = None,
    body: dict | None = None,
) -> dict[str, Any]:
    url = _build_url(path, query)
    headers = {
        "api-key": _resolve_api_key(),
        "Accept": "application/json",
        "User-Agent": "rocketlane-mcp/1.0",
    }
    data: bytes | None = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=data, method=method.upper(), headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=_SSL_CONTEXT) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = resp.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace") if e.fp else ""
        status = e.code
    except urllib.error.URLError as e:
        return {"status": 0, "error": True, "body": {"message": f"network failure: {e.reason}"}}

    if raw:
        try:
            body_out: Any = json.loads(raw)
        except json.JSONDecodeError:
            body_out = {"_raw": raw}
    else:
        body_out = {}

    result: dict[str, Any] = {"status": status, "body": body_out}
    if status >= 400:
        result["error"] = True
    return result


# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------

mcp = FastMCP("rocketlane")


@mcp.tool()
def rocketlane_request(
    method: str,
    path: str,
    query: dict | None = None,
    body: dict | None = None,
) -> dict[str, Any]:
    """
    Generic Rocketlane API call. Use for any endpoint not covered by a named tool.

    Args:
        method: HTTP method — GET, POST, PUT, PATCH, DELETE.
        path: API path beginning with "/" (e.g. "/projects", "/tasks/4821").
        query: Filter & pagination params using Rocketlane filter syntax.
            Examples: {"projectName.cn": "Acme", "pageSize": 25},
                      {"projectStatus.eq": "ACTIVE", "pageToken": "..."}.
        body: JSON body for POST/PUT/PATCH.

    Returns:
        {"status": int, "body": <parsed JSON>, "error": bool (only on 4xx/5xx)}
    """
    return _call(method, path, query, body)


@mcp.tool()
def rocketlane_get_all(
    path: str,
    query: dict | None = None,
    max_pages: int = 20,
) -> dict[str, Any]:
    """
    Auto-paginate a Rocketlane list endpoint. Follows pageToken until exhausted
    or max_pages reached. Use only when the user clearly wants the full set.

    Returns:
        {"status": 200, "body": {"data": [...], "pages_fetched": N, "truncated": bool}}
        — or the raw error dict on any non-2xx page.
    """
    q: dict[str, Any] = dict(query or {})
    q.setdefault("pageSize", 100)
    merged: list[Any] = []
    pages = 0
    truncated = False
    while True:
        result = _call("GET", path, q)
        if result.get("error"):
            return result
        body = result["body"] if isinstance(result.get("body"), dict) else {}
        data = body.get("data")
        if data is None:
            data = body.get("results", [])
        if isinstance(data, list):
            merged.extend(data)
        pages += 1
        token = body.get("pageToken") or body.get("nextPageToken")
        if not token:
            break
        if pages >= max_pages:
            truncated = True
            break
        q["pageToken"] = token
    return {
        "status": 200,
        "body": {"data": merged, "pages_fetched": pages, "truncated": truncated},
    }


# --- Named convenience tools (most common Sales SE reads) ------------------

def _paginated(extra: dict[str, Any] | None, page_size: int, page_token: str | None) -> dict[str, Any]:
    q: dict[str, Any] = dict(extra or {})
    q["pageSize"] = page_size
    if page_token:
        q["pageToken"] = page_token
    return q


@mcp.tool()
def list_projects(
    filters: dict | None = None,
    page_size: int = 25,
    page_token: str | None = None,
) -> dict[str, Any]:
    """
    List Rocketlane projects.

    Common filters (Rocketlane filter syntax — `field.operation`):
      projectName.cn   contains, e.g. {"projectName.cn": "Dafiti"}
      projectStatus.eq ACTIVE | ARCHIVED | ON_HOLD | COMPLETED
      customer.eq      customer ID
      owner.eq         owner user ID
    """
    return _call("GET", "/projects", _paginated(filters, page_size, page_token))


@mcp.tool()
def get_project(project_id: int | str) -> dict[str, Any]:
    """Get a single Rocketlane project by ID, including owner, customer, dates, status."""
    return _call("GET", f"/projects/{project_id}")


@mcp.tool()
def list_project_phases(project_id: int | str) -> dict[str, Any]:
    """List phases for a project."""
    return _call("GET", f"/projects/{project_id}/phases")


@mcp.tool()
def list_project_members(project_id: int | str) -> dict[str, Any]:
    """List members assigned to a project."""
    return _call("GET", f"/projects/{project_id}/members")


@mcp.tool()
def list_tasks(
    project_id: int | str | None = None,
    filters: dict | None = None,
    page_size: int = 25,
    page_token: str | None = None,
) -> dict[str, Any]:
    """
    List tasks. Pass project_id to scope to a single project.

    Common filters: taskName.cn, taskStatus.eq, assignee.eq, dueDate.lte, dueDate.gte.
    """
    q = dict(filters or {})
    if project_id is not None:
        q["projectId.eq"] = project_id
    return _call("GET", "/tasks", _paginated(q, page_size, page_token))


@mcp.tool()
def get_task(task_id: int | str) -> dict[str, Any]:
    """Get a single task by ID."""
    return _call("GET", f"/tasks/{task_id}")


@mcp.tool()
def list_users(
    filters: dict | None = None,
    page_size: int = 25,
    page_token: str | None = None,
) -> dict[str, Any]:
    """
    List users / team members.

    Common filters: emailId.eq, firstName.cn, lastName.cn, type.eq (TEAM_MEMBER, CUSTOMER).
    """
    return _call("GET", "/users", _paginated(filters, page_size, page_token))


@mcp.tool()
def get_user(user_id: int | str) -> dict[str, Any]:
    """Get a user by ID."""
    return _call("GET", f"/users/{user_id}")


@mcp.tool()
def list_invoices(
    filters: dict | None = None,
    page_size: int = 25,
    page_token: str | None = None,
) -> dict[str, Any]:
    """List invoices. Common filters: invoiceStatus.eq, projectId.eq, dueDate.lte/gte."""
    return _call("GET", "/invoices", _paginated(filters, page_size, page_token))


@mcp.tool()
def list_time_entries(
    filters: dict | None = None,
    page_size: int = 25,
    page_token: str | None = None,
) -> dict[str, Any]:
    """List time entries. Common filters: userId.eq, projectId.eq, taskId.eq, date.gte/lte."""
    return _call("GET", "/time-entries", _paginated(filters, page_size, page_token))


# ---------------------------------------------------------------------------
# High-level SE analytics tools (server-side pull + aggregate → small result).
#
# These give the Desktop copilot fast, reliable portfolio analytics WITHOUT the
# in-chat 1MB/pagination wall: the whole pipeline runs here (outside the sandbox)
# and returns only the small final result. Same analyze.py used by the Claude
# Code `rocketlane` skill — single source of the win-rate/report/health logic.
# ---------------------------------------------------------------------------

import sys as _sys  # noqa: E402

_sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import analyze as _analyze  # noqa: E402
except Exception:  # pragma: no cover
    _analyze = None


def _pull_all_projects(updated_since_ms: int | None = None, max_pages: int = 40) -> dict[str, Any]:
    """Paginated /projects pull with archived + all custom fields (~8 calls)."""
    q: dict[str, Any] = {"includeArchive.eq": "true", "includeAllFields": "true", "pageSize": 100}
    if updated_since_ms is not None:
        q["updatedAt.ge"] = int(updated_since_ms)
    out: list[Any] = []
    pages = 0
    total = None
    while True:
        res = _call("GET", "/projects", q)
        if res.get("error"):
            return {"error": res}
        body = res["body"] if isinstance(res.get("body"), dict) else {}
        data = body.get("data") or body.get("results") or []
        if isinstance(data, list):
            out.extend(data)
        pagination = body.get("pagination") if isinstance(body.get("pagination"), dict) else body
        if total is None:
            total = pagination.get("totalRecordCount")
        pages += 1
        token = pagination.get("nextPageToken")
        if not token or pages >= max_pages:
            break
        q["pageToken"] = token
    return {"projects": out, "total": total, "pages": pages}


def _se_items(pulled: dict) -> list:
    return _analyze.scope_se(_analyze.rows_from_projects(pulled["projects"]))


def _weekly_baseline(target_days: int = 7, min_days: int = 4):
    """Read the skill's snapshot cache (~/.cache/rocketlane) for a ~7-day-ago baseline, for
    week-over-week highlight/lowlight. Returns {'items', 'as_of'} or None (insufficient history
    = no snapshot at least `min_days` old). The MCP is stateless per call but co-located with
    the deterministic pipeline's snapshot store, so it reads that store rather than keeping its own."""
    if _analyze is None:
        return None
    import datetime as _dt
    import glob as _glob
    cache = Path.home() / ".cache" / "rocketlane"
    now = _dt.datetime.now()
    best = None
    for path in sorted(_glob.glob(str(cache / "snapshot-*.json"))):
        try:
            snap = json.loads(Path(path).read_text())
            as_of = (snap.get("as_of") or "")[:19]
            if not as_of:
                continue
            age = (now - _dt.datetime.fromisoformat(as_of)).days
            if age < min_days:
                continue
            score = abs(age - target_days)
            if best is None or score < best[0]:
                best = (score, snap)
        except Exception:
            continue
    if best is None:
        return None
    snap = best[1]
    return {"items": _analyze.scope_se(_analyze.rows_from_projects(snap["projects"])),
            "as_of": snap.get("as_of")}


def _with_since(out: dict, baseline) -> dict:
    """Stamp the movement block's `since` with the baseline's as_of, when movement was computed."""
    if baseline and isinstance(out.get("movement"), dict) and out["movement"].get("status") == "ok":
        out["movement"]["since"] = baseline["as_of"]
    return out


@mcp.tool()
def get_se_winrate(from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
    """
    SE-team win-rate (opps from Template SE, templateId 520608). Runs the full
    pull+aggregate server-side and returns a SMALL result (no 1MB wall).

    Args:
        from_date / to_date: 'YYYY-MM-DD' window. Defaults to the current calendar
        half. For H1 2026 pass from_date=2026-01-01, to_date=2026-06-30.

    Returns: {won, lost, strict, sensitivity, top_lost[...], loss_reason_fill, _provenance}.
    """
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    pulled = _pull_all_projects()
    if "error" in pulled:
        return pulled
    import datetime as _dt
    today = _dt.datetime.now().strftime("%Y-%m-%d")
    start, end = (from_date, to_date) if from_date and to_date else _analyze.current_half(today)
    wr = _analyze.winrate(_se_items(pulled), start, end)
    wr["_provenance"] = {"source": "local MCP api-key", "universe": pulled["total"]}
    return wr


@mcp.tool()
def get_se_report() -> dict[str, Any]:
    """SE×Stage and Macro Region×Stage matrices (count + ACV) for Template SE opps. Server-side."""
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    pulled = _pull_all_projects()
    if "error" in pulled:
        return pulled
    out = _analyze.report(_se_items(pulled))
    out["_provenance"] = {"source": "local MCP api-key", "universe": pulled["total"]}
    return out


@mcp.tool()
def get_se_health() -> dict[str, Any]:
    """SE portfolio hygiene: no-stage, Salesforce-owned, closed-missing-date, ACV-0, dups. Server-side."""
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    pulled = _pull_all_projects()
    if "error" in pulled:
        return pulled
    out = _analyze.health(_se_items(pulled))
    out["_provenance"] = {"source": "local MCP api-key", "universe": pulled["total"]}
    return out


def _digest_prov(out: dict, pulled: dict) -> dict:
    out["_provenance"] = {"source": "local MCP api-key", "universe": pulled["total"]}
    return out


@mcp.tool()
def get_exec_digest(from_date: str | None = None, to_date: str | None = None) -> dict[str, Any]:
    """
    VP dashboard, server-side → small result: data-quality scorecard by Macro Region, org
    win-rate TREND across recent halves (strict + sensitivity), the Region×Stage
    open-pipeline funnel, and org-wide SE×Phase (task-inferred playbook progress, each SE
    tagged with the region(s) they have projects in). Every block carries its
    coverage/denominator. Optional from_date/to_date ('YYYY-MM-DD') pins the win-rate
    window instead of the trend.

    Pipeline, stage, ACV, owner and region come from the weekly Salesforce export (fixed
    Drive-synced path — see validate_sf_pipeline), NOT Rocketlane's synced fields:
    Rocketlane allows manually-created/edited projects that silently diverge from
    Salesforce (a real $20M-vs-$67K discrepancy motivated this). See
    orphan_rocketlane_projects for Rocketlane records with no matching SF opportunity,
    exactly the failure mode above.

    se_by_phase is the one exception: it is computed ENTIRELY from Rocketlane's own
    project list and project status, never joined through Salesforce — an sfid join would
    silently lose most Rocketlane projects (many have no matching SF row) and misreport
    them as "Unknown". Columns: Discovery Meeting / RFP / Demo / POC / Solution Design /
    Closing/Handover / Unknown (phase, only for projects whose Rocketlane status is "In
    progress") plus Backlog / On Hold / Completed / Cancelled (project status, everyone
    else — no phase is inferred for a project that isn't active). Spans the WHOLE org
    (not one region) — the task fetch is correspondingly larger than get_region_digest's,
    still cache-first, bounded-concurrency, and limited to "In progress" projects only.
    Partial per-project fetch failures never fail the call; that project buckets "Unknown"
    and the count is at _provenance.task_fetch_failures.
    """
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    sfb = _sf_backed_digest(None)
    if isinstance(sfb, dict) and "error" in sfb:
        return sfb
    sf_items, tasks_by_project, failed, orphans, sf_as_of, rl_items_scope = sfb
    import datetime as _dt
    today = _dt.datetime.now().strftime("%Y-%m-%d")
    out = _analyze.exec_digest(sf_items, today, from_date, to_date,
                               prev_items=None, tasks_by_project=tasks_by_project,
                               rl_items=rl_items_scope)
    out["orphan_rocketlane_projects"] = {"count": len(orphans), "top": orphans[:10]}
    out["_provenance"] = {"source": "Salesforce weekly export + Rocketlane (se_by_phase only)",
                          "sf_universe": len(sf_items), "sf_pipeline_as_of": sf_as_of,
                          "task_fetch_failures": len(failed)}
    return out


@mcp.tool()
def get_region_digest(macro_region: str) -> dict[str, Any]:
    """
    Macro-Region leader digest, server-side: open-pipeline funnel by stage,
    data-completeness by SE, SE x Stage AND SE x Phase (task-inferred playbook progress)
    breakdowns, and at-risk = opps whose Opp Closed Date is past but stage is still open.
    macro_region e.g. "EMEA-APAC", "Brazil", "North LATAM", "South LATAM", "USA".

    Pipeline, stage, ACV, owner and region come from the weekly Salesforce export (fixed
    Drive-synced path — see validate_sf_pipeline), NOT Rocketlane's synced fields — see
    get_exec_digest's docstring for why. orphan_rocketlane_projects surfaces Rocketlane
    records in this region with no matching SF opportunity.

    se_by_phase is the one exception: computed ENTIRELY from Rocketlane's own project
    list and project status (not joined through Salesforce — see get_exec_digest's
    docstring). Columns: the 6 phase buckets (only for projects whose Rocketlane status
    is "In progress") plus Backlog / On Hold / Completed / Cancelled for everyone else.
    Phase is inferred from playbook task completion status via a bounded-concurrency
    /tasks fetch per "In progress" project, cached ~15 min in
    ~/.cache/rocketlane/tasks_cache.json. A per-project task-fetch failure never fails
    the whole call — that project just buckets "Unknown"; failure count is at
    _provenance.task_fetch_failures.
    """
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    sfb = _sf_backed_digest(macro_region)
    if isinstance(sfb, dict) and "error" in sfb:
        return sfb
    sf_items, tasks_by_project, failed, orphans, sf_as_of, rl_items_scope = sfb
    import datetime as _dt
    today = _dt.datetime.now().strftime("%Y-%m-%d")
    out = _analyze.region_digest(sf_items, macro_region, today,
                                 prev_items=None, tasks_by_project=tasks_by_project,
                                 rl_items=rl_items_scope)
    out["orphan_rocketlane_projects"] = {"count": len(orphans), "top": orphans[:10]}
    out["_provenance"] = {"source": "Salesforce weekly export + Rocketlane (se_by_phase only)",
                          "sf_universe": len(sf_items), "sf_pipeline_as_of": sf_as_of,
                          "task_fetch_failures": len(failed)}
    return out


@mcp.tool()
def get_se_digest(email: str) -> dict[str, Any]:
    """
    Individual SE digest (Template SE), server-side: data-hygiene nudges (my opps missing
    stage / close date / ACV), my open pipeline by stage, and this SE's own week-over-week
    movement (won/lost/advanced since the last weekly snapshot — "insufficient_history" until
    a baseline ~7 days old exists). Matches on owner email OR team membership.
    email e.g. "felipe.dias@vtex.com".
    """
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    pulled = _pull_all_projects()
    if "error" in pulled:
        return pulled
    import datetime as _dt
    today = _dt.datetime.now().strftime("%Y-%m-%d")
    bl = _weekly_baseline()
    out = _analyze.se_digest(_se_items(pulled), email, today,
                             prev_items=(bl["items"] if bl else None))
    return _digest_prov(_with_since(out, bl), pulled)


_ALERT_STATE_STORE = Path.home() / ".cache" / "rocketlane" / "alert_state.json"


def _load_alert_state(email: str) -> dict:
    try:
        return json.loads(_ALERT_STATE_STORE.read_text()).get(email, {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_alert_state(email: str, state: dict) -> None:
    try:
        all_state = json.loads(_ALERT_STATE_STORE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        all_state = {}
    all_state[email] = state
    _ALERT_STATE_STORE.parent.mkdir(parents=True, exist_ok=True)
    _ALERT_STATE_STORE.write_text(json.dumps(all_state, indent=2))


_TASKS_CACHE_STORE = Path.home() / ".cache" / "rocketlane" / "tasks_cache.json"
_TASKS_CACHE_TTL_S = 15 * 60


def _load_tasks_cache() -> dict:
    try:
        return json.loads(_TASKS_CACHE_STORE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_tasks_cache(cache: dict) -> None:
    _TASKS_CACHE_STORE.parent.mkdir(parents=True, exist_ok=True)
    _TASKS_CACHE_STORE.write_text(json.dumps(cache, indent=2))


_SF_PIPELINE_PATH = Path(os.environ.get("SF_PIPELINE_PATH") or (
    "/Users/stq/Library/CloudStorage/GoogleDrive-noe.eustaquio@vtex.com/"
    "Unidades compartidas/Solution Engineering Global/SE Opps/"
    "SE Co-pilot Governance Agent/Reports/SalesForce weekly/SF_pipeline.csv"
))


def _load_sf_pipeline():
    """Read + parse the weekly SF export directly from its fixed Drive-synced path —
    no caching, no separate ingest step: the file is small (~375 rows) so re-parsing on
    every call is negligible cost and always reflects whatever Drive last synced. Returns
    {"items", "report", "as_of"} (as_of = the file's own last-modified time, the real
    freshness signal) or None if the path doesn't exist (Drive not synced on this
    machine, or the file was moved)."""
    if not _SF_PIPELINE_PATH.is_file():
        return None
    text = _SF_PIPELINE_PATH.read_text(encoding="utf-8-sig")
    items, report = _analyze.parse_sf_pipeline_csv(text)
    import datetime as _dt
    as_of = _dt.datetime.fromtimestamp(_SF_PIPELINE_PATH.stat().st_mtime).isoformat()
    return {"items": items, "report": report, "as_of": as_of}


@mcp.tool()
def validate_sf_pipeline() -> dict[str, Any]:
    """Quick read-only check of the current weekly Salesforce pipeline export (fixed
    Drive-synced path — override with the SF_PIPELINE_PATH env var) — row count, any
    owner name or country not yet in SF_NAME_MAP/SF_COUNTRY_TO_MACRO (analyze.py),
    duplicate or missing Opportunity IDs, and the file's last-modified time. Does NOT
    pull Rocketlane — use this for a fast sanity check right after the weekly file
    refreshes, before running get_exec_digest/get_region_digest."""
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    sf = _load_sf_pipeline()
    if sf is None:
        return {"error": f"SF pipeline file not found at {_SF_PIPELINE_PATH} — check Drive sync"}
    return {"as_of": sf["as_of"], "source_file": str(_SF_PIPELINE_PATH), **sf["report"]}


import threading as _threading  # noqa: E402

# Global pacer for /tasks fetches: Rocketlane caps non-GET-all calls at 400/min
# (README.md/docs/endpoints.md). A ThreadPoolExecutor with several concurrent workers
# dispatches far faster than that once responses are quick (observed: 8 workers over a
# large org-wide batch produced ~1200/min and a wave of 429s -> most projects falling
# back to "Unknown"). This lock+timestamp pair serializes dispatch so no matter how many
# threads are racing to fetch, requests leave at most every _TASKS_MIN_INTERVAL_S apart —
# a safety margin under the real cap, shared globally across all callers in this process.
_TASKS_RATE_LOCK = _threading.Lock()
_TASKS_LAST_DISPATCH = [0.0]
_TASKS_MIN_INTERVAL_S = 60.0 / 300  # 300/min sustained, ~25% margin under the 400/min cap


def _tasks_rate_limit_wait() -> None:
    import time
    with _TASKS_RATE_LOCK:
        now = time.time()
        wait = _TASKS_LAST_DISPATCH[0] + _TASKS_MIN_INTERVAL_S - now
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        _TASKS_LAST_DISPATCH[0] = now


def _fetch_tasks_for_project(pid: str, max_pages: int = 5, max_retries: int = 4) -> list[dict]:
    """All tasks for one project, following nextPageToken defensively (observed 12-16
    tasks/project live, so pageSize=100 is almost always a single page). Every request
    (including retries) goes through the global rate limiter; a 429/error retries with
    exponential backoff before giving up."""
    import time
    out: list[dict] = []
    q: dict[str, Any] = {"projectId.eq": pid, "pageSize": 100}
    pages = 0
    while True:
        res = None
        for attempt in range(max_retries):
            _tasks_rate_limit_wait()
            res = _call("GET", "/tasks", q)
            if not res.get("error"):
                break
            time.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s
        if res.get("error"):
            raise RuntimeError(f"tasks fetch failed for project {pid} after {max_retries} attempts: {res}")
        body = res["body"] if isinstance(res.get("body"), dict) else {}
        data = body.get("data") or body.get("results") or []
        if isinstance(data, list):
            out.extend(data)
        pagination = body.get("pagination") if isinstance(body.get("pagination"), dict) else body
        token = pagination.get("nextPageToken")
        pages += 1
        if not token or pages >= max_pages:
            break
        q["pageToken"] = token
    return out


def _fetch_tasks_bounded(project_ids: list[str], max_workers: int = 8) -> tuple[dict[str, list[dict]], list[str]]:
    """tasks_by_project, cache-first (TTL _TASKS_CACHE_TTL_S), fanning cache MISSES out
    over a bounded ThreadPoolExecutor (_call is blocking I/O — safe to parallelize with
    threads; well within the 400/min non-GET-all rate limit even at 8-10 workers over a
    full region). Returns (tasks_by_project, failed_project_ids) — a failed project's
    tasks are simply absent, never raised past this function."""
    import time
    import concurrent.futures as cf
    now = time.time()
    cache = _load_tasks_cache()
    tasks_by_project: dict[str, list[dict]] = {}
    to_fetch: list[str] = []
    for pid in project_ids:
        entry = cache.get(pid)
        if entry and (now - entry.get("as_of_epoch", 0)) < _TASKS_CACHE_TTL_S:
            tasks_by_project[pid] = entry["tasks"]
        else:
            to_fetch.append(pid)

    failed: list[str] = []
    if to_fetch:
        with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
            future_to_pid = {ex.submit(_fetch_tasks_for_project, pid): pid for pid in to_fetch}
            for fut in cf.as_completed(future_to_pid):
                pid = future_to_pid[fut]
                try:
                    tasks = fut.result()
                except Exception:
                    failed.append(pid)
                    continue
                tasks_by_project[pid] = tasks
                cache[pid] = {"as_of_epoch": now, "tasks": tasks}
        _save_tasks_cache(cache)
    return tasks_by_project, failed


def _sf_backed_digest(macro_filter: str | None):
    """Read the weekly SF pipeline export (fixed Drive-synced path) for
    pipeline/stage/ACV/owner/region, and separately pull Rocketlane's own SE project list
    for se_by_phase and orphan detection. se_by_phase is intentionally NOT joined through
    Salesforce (an sfid join loses ~70% of Rocketlane projects that have no matching SF
    row, which used to collapse them all into a false "Unknown" phase) — it runs entirely
    on Rocketlane's own item list and Rocketlane's own project id, keyed straight off
    _fetch_tasks_bounded with no re-keying. Only "In progress" projects need a task fetch
    at all (project_status_bucket) — Backlog/On Hold/Completed/Cancelled are counted by
    status alone, no phase to infer.

    orphan_rocketlane_projects (Rocketlane records with no matching SF opportunity) is the
    governance signal this whole change exists to catch: a manually-created/edited
    Rocketlane project disconnected from Salesforce reality. Returns
    (sf_items, tasks_by_project, failed, orphans, sf_as_of, rl_items_scope) or an
    {"error": ...} dict."""
    sf = _load_sf_pipeline()
    if sf is None:
        return {"error": f"SF pipeline file not found at {_SF_PIPELINE_PATH} — check Drive sync"}
    sf_items = sf["items"]
    if macro_filter:
        sf_items = [(sfid, r) for sfid, r in sf_items if r["macro"] == macro_filter]
    sf_sfids = {_analyze.norm_sfid(r["sfid"]) for _, r in sf_items if _analyze.norm_sfid(r["sfid"])}

    rl_pulled = _pull_all_projects()
    if "error" in rl_pulled:
        return rl_pulled
    rl_items = _se_items(rl_pulled)
    if macro_filter:
        rl_items_scope = [(pid, r) for pid, r in rl_items if r["macro"] == macro_filter]
    else:
        rl_items_scope = rl_items

    pids_needed = sorted({pid for pid, r in rl_items_scope
                          if _analyze.project_status_bucket(r.get("status")) == "In progress"})
    tasks_by_project, failed = _fetch_tasks_bounded(pids_needed)

    orphans = _analyze.orphan_rocketlane_projects(rl_items_scope, sf_sfids)
    return sf_items, tasks_by_project, failed, orphans, sf["as_of"], rl_items_scope


@mcp.tool()
def get_stalled_alerts(email: str) -> dict[str, Any]:
    """
    Trigger #1 (stalled-opp alert), deduped: returns ONLY the overdue opportunities that are
    NEW since the last call for this email, or whose overdue severity crossed a new 30-day
    threshold, or whose project status changed — never the same unchanged alert twice in a
    row. Designed for a DAILY Cowork schedule: call this (not `get_se_digest`) for the
    alert use case, and only send a Slack DM when `alerts` is non-empty.

    Persists per-email alert state in ~/.cache/rocketlane/alert_state.json between calls
    (this MCP is otherwise stateless). email e.g. "djan.magno@vtex.com".

    Scoped strictly to opportunities this email OWNS (unlike get_se_digest's "my book", which
    also includes opps where you're just a team member) — an alert must always DM the actual
    owner, never a teammate who happens to share the project.

    Returns: {alerts: [...], count, _provenance}. Each alert has projectId, name, stage,
    acv, closed_forecast, macro, owner, status, overdue_days.
    """
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    pulled = _pull_all_projects()
    if "error" in pulled:
        return pulled
    import datetime as _dt
    today = _dt.datetime.now().strftime("%Y-%m-%d")
    items = _se_items(pulled)
    e = (email or "").lower()
    owned = [(p, r) for p, r in items if r["owner_email"].lower() == e]
    overdue = _analyze.overdue(owned, today)["opps"]
    prev_state = _load_alert_state(email)
    alerts, new_state = _analyze.stalled_alerts(overdue, prev_state, today)
    _save_alert_state(email, new_state)
    return {"alerts": alerts, "count": len(alerts),
            "_provenance": {"source": "local MCP api-key", "universe": len(items), "as_of": today}}


# ---------------------------------------------------------------------------
# Presentation artifacts (render + URL registry)
# ---------------------------------------------------------------------------

try:
    import render as _render  # noqa: E402
except Exception:  # pragma: no cover
    _render = None

_URL_STORE = Path.home() / ".cache" / "rocketlane" / "artifact_urls.json"


def _url_key(view: str, region: str | None) -> str:
    return f"region:{region}" if view == "region" else view


def _load_urls() -> dict:
    try:
        return json.loads(_URL_STORE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


@mcp.tool()
def get_artifact_url(view: str, region: str | None = None) -> dict[str, Any]:
    """Canonical bookmarked artifact URL for a view ('exec'|'region'|'se'), if one was
    published before. Region needs `region`. Returns {url} or {url: null}. Used by the
    scheduled Cowork task to REDEPLOY to the same URL (stable bookmark), not mint a new one."""
    return {"key": _url_key(view, region), "url": _load_urls().get(_url_key(view, region))}


@mcp.tool()
def set_artifact_url(view: str, url: str, region: str | None = None) -> dict[str, Any]:
    """Persist the artifact URL for a view after (re)publishing, so future runs redeploy to
    the same URL. Call this right after creating/updating the artifact."""
    urls = _load_urls()
    urls[_url_key(view, region)] = url
    _URL_STORE.parent.mkdir(parents=True, exist_ok=True)
    _URL_STORE.write_text(json.dumps(urls, indent=2))
    return {"ok": True, "key": _url_key(view, region), "url": url}


@mcp.tool()
def render_presentation(view: str, region: str | None = None, se: str | None = None) -> dict[str, Any]:
    """
    Build a SELF-CONTAINED HTML presentation artifact (screen-share-ready dashboard) for
    Template SE numbers. view: 'exec' (org) | 'region' (needs `region`, e.g. "EMEA-APAC")
    | 'se' (needs `se` email). Returns {html, view, url, instructions}.

    IMPORTANT for the caller: create/redeploy an Artifact whose ENTIRE content is the
    returned `html`, VERBATIM — never retype numbers, never edit the HTML. Numbers are
    checksum-protected (a red banner fires if the blob is corrupted). Then call
    `set_artifact_url(view, url[, region])` with the resulting artifact URL, and (scheduled
    runs) post that URL to the audience's Slack channel.
    """
    if _analyze is None:
        return {"error": "analyze module unavailable next to server.py"}
    if _render is None:
        return {"error": "render module unavailable next to server.py"}
    import datetime as _dt
    now = _dt.datetime.now()
    today = now.strftime("%Y-%m-%d")
    task_fetch_failures = 0
    sf_as_of = None
    if view == "exec":
        sfb = _sf_backed_digest(None)
        if isinstance(sfb, dict) and "error" in sfb:
            return sfb
        sf_items, tasks_by_project, failed, orphans, sf_as_of, rl_items_scope = sfb
        task_fetch_failures = len(failed)
        digest = _analyze.exec_digest(sf_items, today, prev_items=None,
                                      tasks_by_project=tasks_by_project, rl_items=rl_items_scope)
        digest["orphan_rocketlane_projects"] = {"count": len(orphans), "top": orphans[:10]}
    elif view == "region":
        if not region:
            return {"error": "region required for view='region' (e.g. 'EMEA-APAC')"}
        sfb = _sf_backed_digest(region)
        if isinstance(sfb, dict) and "error" in sfb:
            return sfb
        sf_items, tasks_by_project, failed, orphans, sf_as_of, rl_items_scope = sfb
        task_fetch_failures = len(failed)
        digest = _analyze.region_digest(sf_items, region, today, prev_items=None,
                                        tasks_by_project=tasks_by_project, rl_items=rl_items_scope)
        digest["orphan_rocketlane_projects"] = {"count": len(orphans), "top": orphans[:10]}
    elif view == "se":
        if not se:
            return {"error": "se (email) required for view='se'"}
        pulled = _pull_all_projects()
        if "error" in pulled:
            return pulled
        items = _se_items(pulled)
        digest = _analyze.se_digest(items, se, today)
    else:
        return {"error": "view must be 'exec' | 'region' | 'se'"}
    if view in ("region", "exec"):
        prov = {"source": "Salesforce weekly export + Rocketlane (se_by_phase only)",
                "as_of": now.strftime("%Y-%m-%dT%H:%M:%S"), "sf_pipeline_as_of": sf_as_of,
                "task_fetch_failures": task_fetch_failures}
    else:
        prov = {"source": "local MCP api-key", "as_of": now.strftime("%Y-%m-%dT%H:%M:%S"),
                "universe": pulled["total"]}
    html = _render.build_artifact(view, digest, prov, now.strftime("%Y-%m-%dT%H:%M:%S"))
    key = _url_key(view, region)
    return {"view": view, "key": key, "html": html, "url": _load_urls().get(key),
            "instructions": "Create/redeploy an artifact whose ENTIRE content is `html`, "
                            "verbatim. Then call set_artifact_url(view, url[, region])."}


@mcp.tool()
def post_slack_dm(recipient: str, text: str) -> dict[str, Any]:
    """
    DM a person in Slack via the team's bot identity ("SE Co-Pilot Agent"), not as the
    connected Claude account. `recipient` is a Slack user id (U...) or an email (resolved
    via users.lookupByEmail). Requires SLACK_BOT_TOKEN (env or credentials.json) — never
    logs the token.

    Use this for scheduled/unattended digests (e.g. a Cowork schedule DMing an SE their own
    get_se_digest) where the message should read as coming from the shared bot, not from
    whoever's Claude account happens to be running the schedule. For interactive chat, the
    standard Slack connector (posts as the user) is usually the right choice instead — this
    tool is specifically for the bot-identity case.
    """
    token = _resolve_slack_token()
    if not token:
        return {"error": True, "message": "SLACK_BOT_TOKEN not found (env or credentials.json)"}
    uid = recipient
    if "@" in recipient:
        r = _slack_lookup_user(recipient, token)
        if r.get("error"):
            return r
        uid = r["user_id"]
    data = json.dumps({"channel": uid, "text": text}).encode("utf-8")
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage", data=data, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + token},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S, context=_SSL_CONTEXT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return {"ok": bool(body.get("ok")), "error": None if body.get("ok") else body.get("error")}
    except urllib.error.URLError as e:
        return {"error": True, "message": f"network failure: {e}"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
