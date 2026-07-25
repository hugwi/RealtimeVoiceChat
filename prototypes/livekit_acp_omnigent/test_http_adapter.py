#!/usr/bin/env python3
"""Test script to run the Voice Gateway HTTP adapter."""

import sys
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent))

from vocis.connectors import ConnectorRegistry
from vocis.connections import PlatformConnectionStore
from vocis.execution import PlatformConnectionExecutor
from vocis.lifecycles import BuiltinLifecycleRegistry
from vocis.credentials import KeyringSecretStore, OmnigentCredentialResolver, HttpxTransport
from vocis.settings_api import VoiceGatewayApi
from voice_gateway_ui.http_adapter import create_app
import httpx
import uvicorn


def main():
    """Create and run the HTTP adapter."""
    # Discover connectors
    registry = ConnectorRegistry.discover([])
    print(f"Discovered {len(registry.list())} connectors")

    # Create connection store
    store_path = Path("/tmp/voice-gateway-test-connections.json")
    store = PlatformConnectionStore(store_path, registry)
    print(f"Connection store initialized at {store_path}")

    # Create credential resolver
    auth_client = httpx.AsyncClient()
    resolver = OmnigentCredentialResolver(
        HttpxTransport(auth_client),
        KeyringSecretStore(),
        client_secret=None,
    )

    # Create executor
    from vocis.lifecycles import RenewableCredentialProvider
    executor = PlatformConnectionExecutor(
        store,
        registry,
        BuiltinLifecycleRegistry(),
        RenewableCredentialProvider(resolver),
    )

    # Create API
    api = VoiceGatewayApi(registry, store, executor)

    # Create FastAPI app
    app = create_app(api)

    # Run server
    print("Starting HTTP adapter on http://127.0.0.1:8788")
    uvicorn.run(app, host="127.0.0.1", port=8788, log_level="info")


if __name__ == "__main__":
    main()
