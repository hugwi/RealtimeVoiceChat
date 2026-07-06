#!/usr/bin/env bash
# Start local voice stack: LiveKit server + agent (ollama brain) + token server
set -e

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SPIKE="$REPO/spike"

echo "=== Starting LiveKit server ==="
nohup "$REPO/bin/livekit-server" --config "$SPIKE/livekit.yaml" \
    >"$REPO/logs/lk-server.log" 2>&1 &
echo "livekit-server pid $!"

echo "=== Starting agent (ollama brain) ==="
nohup env \
    LIVEKIT_URL=ws://localhost:7880 \
    LIVEKIT_API_KEY=devkey \
    LIVEKIT_API_SECRET=secret \
    "$REPO/venv/bin/python" "$SPIKE/agent.py" dev \
    >"$REPO/logs/lk-agent.log" 2>&1 &
echo "agent pid $!"

echo "=== Starting token server on :8080 ==="
nohup env \
    LIVEKIT_API_KEY=devkey \
    LIVEKIT_API_SECRET=secret \
    LIVEKIT_WS_URL="wss://hyggan-system-product-name.tail19f0b5.ts.net:10000" \
    "$REPO/venv/bin/python" "$SPIKE/token_server.py" \
    >"$REPO/logs/lk-tokens.log" 2>&1 &
echo "token_server pid $!"

echo ""
echo "=== Exposing via Tailscale ==="
echo "  wss signaling: tailscale serve --bg --https=10000 http://127.0.0.1:7880"
echo "  token server:  tailscale serve --bg --https=8443  http://127.0.0.1:8080"
echo ""
echo "Run those two serve commands, then build + sideload the Happy app."
echo ""
echo "Logs: $REPO/logs/"
