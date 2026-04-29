# Rocketlane MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that exposes the **Rocketlane REST API v1.0** (64 endpoints — Tasks, Projects, Phases, Time-Offs, Users, Spaces, Time Tracking, Space Documents, Invoices, Fields, Resource Allocations) as tools any MCP-compatible client can call.

Use it from **Claude Desktop**, **Claude Code**, **Cursor**, **Cline**, **Continue**, or any other MCP host to talk to Rocketlane in plain English — list active customer onboardings, pull invoice status, create kickoff tasks, log time entries, and so on.

> **Built for**: Sales SEs, Customer Success Managers, PS / delivery leads, and finance teams who live in Rocketlane and want a conversational layer on top of it.

---

## Features

- **Two implementations, same surface area**:
  - **Python** (`python/server.py`) — built on `FastMCP`. Slim: one generic `rocketlane_request` tool covers all 64 endpoints, plus named convenience tools for the most common reads (projects, tasks, users, invoices, phases, time entries) and an auto-paginating helper.
  - **Node.js** (`node/index.js`) — built on the official `@modelcontextprotocol/sdk`. Every endpoint exposed as its own typed tool (`get_all_projects`, `create_task`, `delete_invoice`, …) — best when you want the LLM to discover capabilities through tool names.
- **Auth**: Rocketlane's `api-key` header, resolved from env var, credentials file, or home directory.
- **Pagination**: respects Rocketlane's `pageSize` / `pageToken` model. The Python server ships an auto-paginate helper.
- **Filtering**: full Rocketlane filter syntax (`field.operation=value`, e.g. `projectStatus.eq=ACTIVE`, `taskName.cn=Acme`).
- **Read / write discipline**: the server itself doesn't gate writes — that's the host's job. Pair this server with a system prompt that requires confirmation before any `POST` / `PUT` / `PATCH` / `DELETE` (see [Safe operating prompt](#safe-operating-prompt) below).

---

## Repository layout

```
rocketlane-mcp/
├── README.md
├── LICENSE
├── .gitignore
├── credentials.example.json     # template — copy to credentials.json and fill in your key
├── python/
│   ├── server.py                # FastMCP server (generic + named tools)
│   ├── requirements.txt
│   └── install.sh               # one-shot venv + pip install + Claude Desktop snippet
├── node/
│   ├── index.js                 # @modelcontextprotocol/sdk server (one tool per endpoint)
│   └── package.json
└── docs/
    ├── endpoints.md             # cheat-sheet of all 64 endpoints
    └── openapi.yaml             # full OpenAPI v3 spec (source of truth for shapes)
```

---

## Prerequisites

- A **Rocketlane API key** — generate it under **Workspace settings → API → Generate token**. The key looks like `rl-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`.
- For the **Python** server: Python ≥ 3.10.
- For the **Node** server: Node.js ≥ 18.

---

## Quick start

### 1. Clone and add your credentials

```bash
git clone https://github.com/VTEX-US-SE/Rocketlane-MCP.git
cd rocketlane-mcp

# Option A — file-based (works for both implementations)
cp credentials.example.json credentials.json
# edit credentials.json and paste your key

# Option B — env var (preferred for Node, also works for Python)
export ROCKETLANE_API_KEY="rl-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

> The Python server resolves the key in this order: `$ROCKETLANE_API_KEY` → `$ROCKETLANE_CREDENTIALS` (path) → `./credentials.json` → `~/.rocketlane/credentials.json`. The Node server **requires** `ROCKETLANE_API_KEY` to be set.

### 2. Install

#### Python

```bash
cd python
./install.sh         # creates .venv, installs mcp, prints the config snippet
```

Or manually:

```bash
cd python
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

#### Node

```bash
cd node
npm install
```

### 3. Wire it into your MCP client

See the [Client integration](#client-integration) section below for Claude Desktop, Claude Code, Cursor, and other hosts.

---

## Client integration

All MCP clients use the same `mcpServers` JSON shape — only the path to the config file differs. Pick the implementation you installed (Python or Node) and drop the matching block into your client's config.

### Claude Desktop

**Config file:**

| OS      | Path                                                                                  |
| ------- | ------------------------------------------------------------------------------------- |
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json`                     |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                                         |
| Linux   | `~/.config/Claude/claude_desktop_config.json`                                         |

**Python:**

```json
{
  "mcpServers": {
    "rocketlane": {
      "command": "/absolute/path/to/rocketlane-mcp/python/.venv/bin/python",
      "args": ["/absolute/path/to/rocketlane-mcp/python/server.py"],
      "env": {
        "ROCKETLANE_API_KEY": "rl-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      }
    }
  }
}
```

**Node:**

```json
{
  "mcpServers": {
    "rocketlane": {
      "command": "node",
      "args": ["/absolute/path/to/rocketlane-mcp/node/index.js"],
      "env": {
        "ROCKETLANE_API_KEY": "rl-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      }
    }
  }
}
```

Quit and reopen Claude Desktop. The `rocketlane` server should appear in the MCP indicator at the bottom of the chat input.

### Claude Code (CLI)

Use the `claude mcp add` command — no manual file editing required:

```bash
# Python
claude mcp add rocketlane \
  --env ROCKETLANE_API_KEY=rl-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  -- /absolute/path/to/rocketlane-mcp/python/.venv/bin/python \
     /absolute/path/to/rocketlane-mcp/python/server.py

# Node
claude mcp add rocketlane \
  --env ROCKETLANE_API_KEY=rl-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  -- node /absolute/path/to/rocketlane-mcp/node/index.js
```

Verify with `claude mcp list`.

### Cursor

Cursor reads `~/.cursor/mcp.json` (or a project-level `.cursor/mcp.json`). Same shape as Claude Desktop:

```json
{
  "mcpServers": {
    "rocketlane": {
      "command": "node",
      "args": ["/absolute/path/to/rocketlane-mcp/node/index.js"],
      "env": {
        "ROCKETLANE_API_KEY": "rl-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
      }
    }
  }
}
```

Restart Cursor. In Composer / Chat, ask "list my active Rocketlane projects" — the agent should call the `get_all_projects` (Node) or `list_projects` (Python) tool.

### Cline / Continue / other VS Code MCP extensions

Most extensions look for a `mcp.json` (or equivalent) in their settings folder. Use the same JSON snippet shown above. Refer to the extension's docs for the exact path.

### Generic stdio MCP host

The server speaks MCP over **stdio**. Any host that can spawn a process and pipe JSON-RPC over stdin/stdout will work — just point it at the launch command:

```bash
ROCKETLANE_API_KEY=rl-... node /path/to/rocketlane-mcp/node/index.js
# or
ROCKETLANE_API_KEY=rl-... /path/to/rocketlane-mcp/python/.venv/bin/python /path/to/rocketlane-mcp/python/server.py
```

---

## Tool surface

### Python (`python/server.py`)

Slim by design. Use `rocketlane_request` for anything not covered by a named tool.

| Tool                     | What it does                                                                                |
| ------------------------ | ------------------------------------------------------------------------------------------- |
| `rocketlane_request`     | Generic call. `method`, `path`, `query`, `body`. Covers all 64 endpoints.                   |
| `rocketlane_get_all`     | Auto-paginates a list endpoint (follows `pageToken` until exhausted or `max_pages` hit).    |
| `list_projects`          | `GET /projects` with filters + pagination.                                                  |
| `get_project`            | `GET /projects/{id}`                                                                        |
| `list_project_phases`    | `GET /projects/{id}/phases`                                                                 |
| `list_project_members`   | `GET /projects/{id}/members`                                                                |
| `list_tasks`             | `GET /tasks` with optional `project_id` scope.                                              |
| `get_task`               | `GET /tasks/{id}`                                                                           |
| `list_users`             | `GET /users`                                                                                |
| `get_user`               | `GET /users/{id}`                                                                           |
| `list_invoices`          | `GET /invoices`                                                                             |
| `list_time_entries`      | `GET /time-entries`                                                                         |

### Node.js (`node/index.js`)

One tool per endpoint — the LLM picks by name. Examples:

- **Tasks**: `get_all_tasks`, `get_task`, `create_task`, `update_task`, `delete_task`, `add_task_assignees`, `move_task_to_phase`, …
- **Projects**: `get_all_projects`, `create_project`, `archive_project`, `import_template_to_project`, …
- **Time tracking**: `get_all_time_entries`, `create_time_entry`, `get_time_entry_categories`, …
- **Invoices**: `get_all_invoices`, `get_invoice_payments`, `get_invoice_line_items`, …
- **Spaces**, **Phases**, **Fields**, **Time-Offs**, **Resource Allocations**, **Users** — full CRUD where the API supports it.

See [`docs/endpoints.md`](docs/endpoints.md) for the full map and [`docs/openapi.yaml`](docs/openapi.yaml) for request/response shapes.

---

## Filter syntax

Rocketlane uses `field.operation=value`. Operations: `eq`, `ne`, `gt`, `lt`, `ge`, `le`, `cn` (contains), `nc` (not contains).

Examples (Python `list_projects`):

```jsonc
// Active projects whose name contains "Acme"
{ "filters": { "projectStatus.eq": "ACTIVE", "projectName.cn": "Acme" } }

// Tasks due before today, assigned to user 87
{ "filters": { "dueDate.lt": "2026-04-28", "assignee.eq": 87 } }
```

Examples (Node — pass as a single string):

```jsonc
{ "filter": "projectStatus.eq=ACTIVE" }
```

**Pagination**: `pageSize` (max 100) + `pageToken`. The response carries `nextPageToken` — pass it in on the next call, or use the Python `rocketlane_get_all` helper to flatten the whole list.

**Rate limits**: 60 req/min for `GET-all`, 400 req/min everywhere else.

---

## Safe operating prompt

The server doesn't gate writes — keep destructive operations behind a confirmation step in the host. A minimal system prompt:

```
You operate on Rocketlane through the rocketlane MCP server.

READ operations (GET): execute immediately, summarize the result.

WRITE operations (POST / PUT / PATCH / DELETE): NEVER call the tool until
the user has explicitly approved. First show:
  - Action (Create / Update / Delete)
  - Resource + ID
  - Endpoint (method + path)
  - Payload preview (only changed fields)
  - Impact (who/what is affected)
End with: "Proceed? (yes / no / edit)". Only on "yes" do you call the tool.

DESTRUCTIVE deletes (Projects, Invoices, Space Documents): require the user
to type the resource name back as a second confirmation.
```

This is the same discipline the project's internal Sales SE assistant uses.

---

## Example prompts

Once the server is wired in, try:

- "List the active Rocketlane projects, owner and customer in a table."
- "What's the status of the Acme onboarding project?"
- "Show me invoices over $50k that are still unpaid."
- "Pull all time entries logged this month against project P-1042."
- "Create a 'Kickoff call' task in the Globex onboarding project, due next Friday." *(write — will ask for confirmation)*
- "Who has time-off scheduled in May?"

---

## Troubleshooting

| Symptom                                                       | Likely cause / fix                                                                                  |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `Rocketlane API key not found`                                | Set `ROCKETLANE_API_KEY` env var, or place `credentials.json` next to the server.                   |
| `401 Unauthorized` from the API                               | Key is wrong, expired, or copied with whitespace. Regenerate in Rocketlane and re-paste.            |
| `429 Too Many Requests`                                       | You hit the 60/min `GET-all` limit. Drop the `rocketlane_get_all` calls or paginate manually.       |
| Claude Desktop doesn't show the server                        | Quit fully (Cmd+Q on macOS), check the config JSON validates, and confirm absolute paths are right. |
| `spawn node ENOENT` / `spawn python ENOENT`                   | Use the absolute path to the binary in the `command` field, not just `node` or `python`.            |
| Server connects but no tools appear                           | Tail the host's MCP log. For Claude Desktop: `~/Library/Logs/Claude/mcp*.log`.                      |

---

## Development

### Run the server standalone (sanity check)

```bash
# Python
ROCKETLANE_API_KEY=rl-... python/.venv/bin/python python/server.py
# It will block on stdin — that's correct. Ctrl+C to exit.

# Node
ROCKETLANE_API_KEY=rl-... node node/index.js
```

### Use the [MCP Inspector](https://github.com/modelcontextprotocol/inspector) to poke at tools interactively:

```bash
npx @modelcontextprotocol/inspector \
  -e ROCKETLANE_API_KEY=rl-... \
  node /absolute/path/to/rocketlane-mcp/node/index.js
```

---

## Security notes

- **Never commit `credentials.json`** — `.gitignore` already excludes it. Only `credentials.example.json` is tracked.
- Treat the API key like a password. It grants the same access the issuing user has in Rocketlane.
- For shared deployments, prefer the env-var path (`ROCKETLANE_API_KEY`) over checked-in files, and rotate keys via Rocketlane workspace settings.


---

## Reference

- Rocketlane developer docs: <https://developer.rocketlane.com>
- OpenAPI spec (bundled): [`docs/openapi.yaml`](docs/openapi.yaml)
- Endpoint cheat-sheet (bundled): [`docs/endpoints.md`](docs/endpoints.md)
- Model Context Protocol: <https://modelcontextprotocol.io>
