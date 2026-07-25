from __future__ import annotations

import argparse
import asyncio
import os
import warnings
from pathlib import Path

from .acp_agent import OmnigentAcpAgent
from .acp_sdk_agent import (
    OfficialSdkAttachedSessionAgent,
    OfficialSdkOmnigentAgent,
)
from .connections import PlatformConnectionError, PlatformConnectionStore
from .connectors import ConnectorManifestError, ConnectorRegistry
from .credentials import (
    CredentialGrantError,
    HttpxTransport,
    KeyringSecretStore,
    OmnigentCredentialResolver,
)
from .execution import ConnectionExecutionError, PlatformConnectionExecutor
from .lifecycles import BuiltinLifecycleRegistry, RenewableCredentialProvider
from .omnigent_backend import OmnigentSdkBackend


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Expose an Agent Platform session as an ACP v1 agent"
    )
    parser.add_argument("--connector", default="omnigent")
    parser.add_argument(
        "--connector-directory",
        action="append",
        default=[],
        help="Trusted directory containing *.connector.json manifests",
    )
    parser.add_argument(
        "--list-connectors",
        action="store_true",
        help="Validate and list discovered Platform Connectors, then exit",
    )
    parser.add_argument(
        "--connection-store",
        default=str(Path("~/.config/voice-gateway/connections.json").expanduser()),
        help="Platform Connection store (default: %(default)s)",
    )
    parser.add_argument(
        "--list-connections",
        action="store_true",
        help="Validate and list configured Platform Connections, then exit",
    )
    parser.add_argument(
        "--connection",
        help="Execute a configured Platform Connection",
    )
    authorization = parser.add_mutually_exclusive_group()
    authorization.add_argument(
        "--authorize-connection",
        metavar="ID",
        help="Authorize an OmniGent Platform Connection with the device flow",
    )
    authorization.add_argument(
        "--revoke-connection",
        metavar="ID",
        help="Revoke an OmniGent Platform Connection's Credential Grant",
    )
    parser.add_argument(
        "--device-client-id",
        default="omnigent-voice-gateway",
        help="OAuth device client id (default: %(default)s)",
    )
    parser.add_argument(
        "--server",
        default="http://127.0.0.1:6767",
        help="Deprecated: OmniGent server URL; use --connection instead",
    )
    parser.add_argument("--session", help="Existing Agent Session id")
    return parser.parse_args()


async def _run() -> None:
    args = parse_args()
    try:
        registry = ConnectorRegistry.discover(args.connector_directory)
        if args.list_connectors:
            for manifest in registry.list():
                capabilities = ",".join(sorted(manifest.capabilities))
                print(
                    f"{manifest.id}\t{manifest.display_name}\t"
                    f"ACP v{manifest.protocol_version}\t{capabilities}"
                )
            return
        if args.list_connections:
            store = PlatformConnectionStore(args.connection_store, registry)
            for connection in store.list():
                print(
                    f"{connection.id}\t{connection.display_name}\t"
                    f"{connection.connector_id}\t{connection.credential_grant_id}"
                )
            return
        if args.authorize_connection or args.revoke_connection:
            store = PlatformConnectionStore(args.connection_store, registry)
            connection_id = args.authorize_connection or args.revoke_connection
            connection = store.get(connection_id)
            if connection.connector_id != "omnigent":
                raise PlatformConnectionError(
                    f"Platform Connection {connection.id!r} does not use OmniGent"
                )
            if connection.credential_grant_id is None:
                raise PlatformConnectionError(
                    f"Platform Connection {connection.id!r} has no Credential Grant"
                )
            server_url = str(connection.configuration["serverUrl"])
            await _manage_device_authorization(
                authorize=args.authorize_connection is not None,
                grant_id=connection.credential_grant_id,
                server_url=server_url,
                client_id=args.device_client_id,
            )
            return
        connection_id = getattr(args, "connection", None)
        if connection_id:
            store = PlatformConnectionStore(args.connection_store, registry)
        else:
            manifest = registry.require(args.connector)
    except (
        ConnectorManifestError,
        CredentialGrantError,
        PlatformConnectionError,
    ) as exc:
        raise SystemExit(str(exc)) from exc

    if connection_id:
        try:
            await _run_connection(args, registry, store)
        except (ConnectionExecutionError, CredentialGrantError) as exc:
            raise SystemExit(str(exc)) from exc
        return

    if args.session is None:
        raise SystemExit(
            "--session is required unless a --list-* operation is used"
        )
    if manifest.id != "omnigent":
        raise SystemExit(
            f"connector {manifest.id!r} is installed but has no in-process adapter"
        )

    from acp import run_agent

    warnings.warn(
        "--server is deprecated; configure a Platform Connection and use "
        "--connection",
        DeprecationWarning,
        stacklevel=2,
    )
    backend = OmnigentSdkBackend(args.server)
    core = OmnigentAcpAgent(backend)
    agent = OfficialSdkOmnigentAgent(core, args.session)
    try:
        await run_agent(agent)
    finally:
        await backend.close()


async def _run_connection(args, registry, store) -> None:
    from acp import run_agent
    import httpx

    auth_client = httpx.AsyncClient()
    try:
        resolver = OmnigentCredentialResolver(
            HttpxTransport(auth_client),
            KeyringSecretStore(),
            client_secret=os.environ.get("OMNIGENT_CLIENT_SECRET"),
        )
        executor = PlatformConnectionExecutor(
            store,
            registry,
            BuiltinLifecycleRegistry(),
            RenewableCredentialProvider(resolver),
        )
        async with executor.execute(
            args.connection, args.session
        ) as execution:
            await run_agent(
                OfficialSdkAttachedSessionAgent(
                    execution.session,
                    execution.agent_session_id,
                )
            )
    finally:
        await auth_client.aclose()


async def _manage_device_authorization(
    *,
    authorize: bool,
    grant_id: str,
    server_url: str,
    client_id: str,
) -> None:
    import httpx

    async with httpx.AsyncClient() as client:
        resolver = OmnigentCredentialResolver(
            HttpxTransport(client),
            KeyringSecretStore(),
            client_secret=os.environ.get("OMNIGENT_CLIENT_SECRET"),
        )
        if not authorize:
            await resolver.revoke(grant_id, server_url=server_url)
            print(f"revoked Credential Grant {grant_id}")
            return

        pending = await resolver.begin(
            grant_id, server_url=server_url, client_id=client_id
        )
        print(f"Open {pending.verification_url}")
        if pending.user_code:
            print(f"Enter code {pending.user_code}")
        while not await resolver.poll(grant_id):
            await asyncio.sleep(pending.poll_interval)
        print(f"authorized Credential Grant {grant_id}")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
