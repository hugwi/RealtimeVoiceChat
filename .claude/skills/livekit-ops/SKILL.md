# LiveKit Operations

LiveKit is the audio transport layer that Vocis integrates with. Vocis itself
is a library — it does not include LiveKit server deployment, systemd units, or
STT/TTS models. Those are external infrastructure.

## What Vocis does with LiveKit

- **`livekit_protocol.py`** — defines the versioned data message protocol (FinalTurn, CancelTurn, PermissionResponse) sent over LiveKit data channels
- **`livekit_adapter.py`** — structurally binds `LiveKitVoiceGateway` to a LiveKit room without importing LiveKit SDK types
- **`gateway.py`** — mediates between LiveKit data messages and the harness backend

## Testing the LiveKit integration

```bash
cd packages/vocis-core

# LiveKit adapter — data messages translated to harness calls
pytest tests/test_livekit_adapter.py -v

# Voice turn tracer — end-to-end message flow
pytest tests/test_tracer.py -v

# Cancellation and permissions
pytest tests/test_cancellation.py -v
pytest tests/test_permissions.py -v

# Full connection execution
pytest tests/test_connection_execution.py -v
```

## How the adapter works

`livekit_adapter.py` binds the gateway to a LiveKit room using duck-typing
(no LiveKit SDK import in the core package):

```python
# The adapter expects the room to provide:
#   room.on("data_received", handler)
#   room.local_participant.publish(data, topic=..., reliable=True)
# It then attaches LiveKitVoiceGateway as the handler.

attach_livekit_gateway(room, gateway)
```

The adapter is pure structural binding — no business logic. All logic lives in
`gateway.py`.

## External LiveKit setup (outside Vocis)

LiveKit server deployment, STT/TTS pipeline, token issuance, and systemd
service management are external infrastructure. Vocis connects to them as a
client, not a server. For the current deployed environment, see
`voice-agent-handoff.md`.
