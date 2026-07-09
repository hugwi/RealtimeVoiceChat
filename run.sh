#!/usr/bin/env bash
# Start all voice-agent services: LiveKit, agent, token server, Happy web
set -e
cd "$(dirname "$0")"

HAPPY_APP="/home/hyggan/happy-src/packages/happy-app"
EXPO_BIN="/home/hyggan/happy-src/node_modules/expo/bin/cli"

# Kill any stale processes
pkill -f "livekit-server" 2>/dev/null || true
pkill -f "spike/agent.py" 2>/dev/null || true
pkill -f "token_server.py" 2>/dev/null || true
pkill -f "expo/bin/cli" 2>/dev/null || true
sleep 1

# 1. LiveKit server
bin/livekit-server --config spike/livekit.yaml > /tmp/livekit.log 2>&1 &
echo "[1/4] LiveKit server started (PID $!)"
sleep 2

# 2. livekit-agents (STT + LLM + TTS)
LIVEKIT_URL=ws://localhost:7880 \
LIVEKIT_API_KEY=devkey \
LIVEKIT_API_SECRET=XhtHLb2P1O6vZBy5uuLEegDQFk-Tg6RcTbTZGzXm840 \
venv/bin/python spike/agent.py dev > /tmp/agent.log 2>&1 &
echo "[2/4] Agent started (PID $!)"

# 3. Token server
venv/bin/python spike/token_server.py > /tmp/token_server.log 2>&1 &
echo "[3/4] Token server started (PID $!)"

# 4. Happy web (Metro)
cd "$HAPPY_APP" && \
  EXPO_NO_BROWSER=1 EXPO_NO_TELEMETRY=1 REACT_NATIVE_INSPECTOR_PROXY=0 CI=1 \
  node "$EXPO_BIN" start --port 8082 > /tmp/expo-web.log 2>&1 &
echo "[4/4] Metro/Happy web started (PID $!)"

echo ""
echo "All services started. Logs: /tmp/{livekit,agent,token_server,expo-web}.log"
echo "Happy web: https://hyggan-system-product-name.tail19f0b5.ts.net:8443/"
echo "Token:     https://hyggan-system-product-name.tail19f0b5.ts.net:8443/token"
echo "LiveKit:   wss://hyggan-system-product-name.tail19f0b5.ts.net:10000"
