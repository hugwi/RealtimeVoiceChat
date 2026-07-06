#!/usr/bin/env bash
# ai-tools/setup.sh
# Bootstrap the AI token-reduction toolchain on a fresh machine.
#
# Idempotent — safe to re-run. Installs and wires:
#   * rtk       — CLI-output compressor (Claude Code / happy PreToolUse hook)
#   * docker    — runtime for the headroom proxy (installed if missing)
#   * headroom  — context-compression proxy Claude Code talks to via a base URL
#
# See ai-tools/README.md for what each tool does and why we use it.
set -euo pipefail

HEADROOM_IMAGE="${HEADROOM_IMAGE:-ghcr.io/chopratejas/headroom:code}"
HEADROOM_PORT="${HEADROOM_PORT:-8787}"
HEADROOM_NAME="${HEADROOM_NAME:-headroom}"
LOCAL_BIN="$HOME/.local/bin"

log()  { printf '\033[0;32m[ai-tools]\033[0m %s\n' "$*"; }
warn() { printf '\033[0;33m[ai-tools]\033[0m %s\n' "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

# 1. rtk -------------------------------------------------------------------
install_rtk() {
  if have rtk; then
    log "rtk present ($(rtk --version)) — skipping download"
  else
    log "installing rtk ..."
    curl -fsSL https://raw.githubusercontent.com/rtk-ai/rtk/refs/heads/master/install.sh | sh
    export PATH="$LOCAL_BIN:$PATH"
  fi
  # Register the global Claude Code / happy PreToolUse hook (idempotent).
  if rtk init --show 2>/dev/null | grep -q '\[ok\] Hook'; then
    log "rtk hook already registered"
  else
    log "registering rtk global hook (~/.claude/settings.json) ..."
    rtk init -g --auto-patch
  fi
}

# 2. docker ----------------------------------------------------------------
install_docker() {
  if have docker; then
    log "docker present ($(docker --version))"
    return
  fi
  warn "docker not found — installing (needs sudo)"
  if have apt-get; then
    sudo apt-get update -y
    sudo apt-get install -y docker.io
    sudo systemctl enable --now docker || true
    sudo usermod -aG docker "$USER" || true
    warn "added $USER to the docker group — log out/in (or run 'newgrp docker') for non-sudo docker"
  else
    warn "no apt-get here; install docker manually: https://docs.docker.com/engine/install/"
    return 1
  fi
}

# 3. headroom proxy --------------------------------------------------------
start_headroom() {
  have docker || { warn "skipping headroom — docker unavailable"; return; }
  local dk="docker"
  docker info >/dev/null 2>&1 || dk="sudo docker"   # group change not active yet

  log "pulling headroom image ($HEADROOM_IMAGE) ..."
  $dk pull "$HEADROOM_IMAGE"

  if $dk ps -a --format '{{.Names}}' | grep -qx "$HEADROOM_NAME"; then
    log "existing headroom container found — recreating"
    $dk rm -f "$HEADROOM_NAME" >/dev/null
  fi

  # Bind to loopback only — the proxy is for this machine's agent, not the network.
  $dk run -d --restart unless-stopped \
    -p "127.0.0.1:${HEADROOM_PORT}:8787" \
    --name "$HEADROOM_NAME" \
    "$HEADROOM_IMAGE"
  log "headroom proxy up on http://127.0.0.1:${HEADROOM_PORT}"
}

main() {
  install_rtk
  install_docker
  start_headroom
  echo
  log "setup complete."
  log "launch happy through headroom:  ai-tools/happy-hr.sh   (or 'happy' for plain)"
  log "rtk savings:  rtk gain          headroom logs:  docker logs $HEADROOM_NAME"
  log "restart happy/Claude Code once so the rtk hook loads."
}
main "$@"
