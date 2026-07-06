#!/usr/bin/env bash
# ai-tools/happy-hr.sh
# Launch happy (Claude Code) routed through the headroom compression proxy.
# happy's native --claude-env flag injects ANTHROPIC_BASE_URL into the spawned
# Claude Code, so requests flow: Claude Code -> headroom (compress) -> Anthropic.
# Falls back to plain happy if the proxy is not reachable.
set -euo pipefail

PORT="${HEADROOM_PORT:-8787}"
URL="http://127.0.0.1:${PORT}"

# curl without -f returns 0 as long as the TCP/HTTP connection is made,
# even on a 4xx — that is enough to know the proxy is listening.
if curl -s -o /dev/null -m 2 "$URL"; then
  echo "[happy-hr] routing through headroom proxy at $URL"
  exec happy --claude-env "ANTHROPIC_BASE_URL=$URL" "$@"
else
  echo "[happy-hr] headroom not reachable at $URL — run ai-tools/setup.sh first; launching plain happy"
  exec happy "$@"
fi
