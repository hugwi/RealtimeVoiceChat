# Adding a New Platform Connector

How to add support for a new Agent Platform (Happier, custom ACP server, etc.).

Follow the reference: `vocis/connectors/builtin/omnigent.connector.json`.

## 1. Create a connector manifest

Add `connectors/builtin/<platform>.connector.json`:

```json
{
  "apiVersion": "voice-gateway/v1alpha1",
  "kind": "AgentPlatformConnector",
  "metadata": {
    "id": "happier",
    "displayName": "Happier",
    "version": "0.1.0"
  },
  "runtime": {
    "type": "executable",
    "command": "happier",
    "arguments": ["acp", "voice-agent"],
    "protocol": "acp",
    "protocolVersion": 1
  },
  "capabilities": {
    "sessionDiscovery": false,
    "sessionHistory": false,
    "streamingText": true,
    "cancellation": true,
    "permissions": false,
    "backgroundTasks": false
  },
  "authentication": {
    "methods": ["bearer-token"],
    "preferred": "bearer-token"
  },
  "configuration": {
    "type": "object",
    "required": ["serverUrl"],
    "properties": {
      "serverUrl": {
        "type": "string",
        "format": "uri",
        "title": "Happier server URL"
      },
      "sessionId": {
        "type": "string",
        "title": "Default agent session ID"
      }
    }
  }
}
```

Validation rules (enforced by `ConnectorRegistry._parse()`):
- `metadata.id`: `^[a-z][a-z0-9-]{1,63}$`
- `metadata.version`: semver
- `runtime.protocol`: only `"acp"` supported
- `capabilities`: object with boolean values — `{sessionDiscovery, sessionHistory, streamingText, cancellation, permissions, backgroundTasks}`
- `authentication.methods`: from `{oauth-device, bearer-token, none}`
- No unknown fields at any nesting level (`_exact_keys()`)

## 2. Implement a lifecycle

Add a lifecycle class in `vocis/lifecycles/__init__.py`:

```python
class HappierConnectorLifecycle:
    connector_id = "happier"

    @asynccontextmanager
    async def connect(self, connection, credential):
        # credential is None for auth "none" connectors
        async with spawn_generic_acp_connector(
            command="happier",
            args=["acp", "voice-agent"],
            session_id=connection.configuration.get("sessionId"),
            cwd=None,
        ) as client:
            yield _HappierPlatform(client)

class _HappierPlatform:
    def __init__(self, client):
        self._client = client

    async def discover_sessions(self):
        raise RuntimeError("sessionDiscovery not advertised")

    async def attach_session(self, session_id):
        return self._client
```

Register it in `BuiltinLifecycleRegistry.__init__`.

## 3. Register a credential resolver (if needed)

If the platform uses OAuth, add a resolver in `vocis/credentials/`.
If it uses bearer tokens (env var), no resolver needed — the lifecycle
reads from config. If it has no auth (`"none"`), the executor skips
credential resolution.

## 4. Wire up in the CLI

Add a new subcommand or connection path in `vocis/__main__.py` if the
platform needs CLI-specific setup (like OmniGent's `--authorize-connection`).

## 5. Add tests

```python
# tests/test_happier_connector.py
# - Manifest validation
# - Lifecycle connect/attach
# - Connection execution with mock backend
```

## 6. Add UI components (optional)

Add platform-specific UI wrappers in `packages/vocis-<platform>/src/ui/`
that compose `@vocis/ui` components with platform-specific styling.

## Reference

Existing connectors for comparison:
- `vocis/connectors/builtin/omnigent.connector.json` — OAuth device flow, attach-only
- `vocis/connectors/builtin/generic-acp.connector.json` — executable ACP subprocess, no auth
- `vocis/lifecycles/__init__.py` — `OmnigentConnectorLifecycle`, `GenericAcpConnectorLifecycle`
