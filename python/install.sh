#!/usr/bin/env bash
# One-shot installer for the rocketlane-mcp server.
# Creates an isolated venv, installs deps, prints the snippet you need to drop
# into Claude Desktop's config so it picks up the MCP on next launch.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PYTHON_BIN="${PYTHON_BIN:-python3}"

echo "==> Creating venv at $VENV"
"$PYTHON_BIN" -m venv "$VENV"

echo "==> Installing dependencies"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -r "$HERE/requirements.txt"

echo "==> Smoke-testing the server module"
"$VENV/bin/python" -c "import server" 2>/dev/null || {
    cd "$HERE" && "$VENV/bin/python" -c "import server" || {
        echo "WARN: import smoke test failed — check $HERE/server.py" >&2
    }
}

CONFIG_PATH="$HOME/Library/Application Support/Claude/claude_desktop_config.json"
SNIPPET=$(cat <<EOF
{
  "mcpServers": {
    "rocketlane": {
      "command": "$VENV/bin/python",
      "args": ["$HERE/server.py"]
    }
  }
}
EOF
)

cat <<EOM

==============================================================================
Install complete.

Next steps:

1. Open (or create) the Claude Desktop config:
     $CONFIG_PATH

2. Merge the following into the top-level "mcpServers" object:

$SNIPPET

3. Quit and reopen the Claude desktop app. The "rocketlane" MCP will load on
   next session start; you'll see its tools available in chat.

Credentials:
  The server reuses the existing key at:
    $HOME/Documents/Claude/Projects/Agent Rocketlane SE/rocketlane-apis/credentials.json
  No further config needed.

Override with env vars if you want:
  ROCKETLANE_API_KEY      — raw key
  ROCKETLANE_CREDENTIALS  — full path to a credentials file

==============================================================================
EOM
