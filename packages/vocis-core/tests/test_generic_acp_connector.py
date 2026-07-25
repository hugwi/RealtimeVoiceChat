from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from vocis.acp_sdk_client import (
    OfficialSdkAcpHarnessClient,
    spawn_omnigent_acp_harness,
)
from vocis.connectors import ConnectorRegistry
from vocis.connectors.generic_acp import (
    GenericAcpClient,
    spawn_generic_acp_connector,
)
from vocis.execution import PlatformConnectionExecutor
from vocis.lifecycles import BuiltinLifecycleRegistry
from vocis.connections import PlatformConnectionStore


class GenericAcpConnectorTests(unittest.TestCase):
    def test_manifest_contract_and_lifecycle_reuse(self) -> None:
        manifest = ConnectorRegistry.discover().require("generic-acp")

        self.assertEqual(manifest.authentication_methods, ("none",))
        self.assertEqual(manifest.runtime_type, "builtin")
        self.assertEqual(manifest.entrypoint, "generic-acp")
        self.assertFalse(manifest.supports("sessionDiscovery"))
        self.assertTrue(manifest.supports("streamingText"))
        self.assertIs(GenericAcpClient, OfficialSdkAcpHarnessClient)
        self.assertIs(spawn_generic_acp_connector, spawn_omnigent_acp_harness)


class GenericAcpExecutableContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_configured_connection_runs_real_acp_subprocess(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manifests = ConnectorRegistry.discover()
            connections = PlatformConnectionStore(
                Path(directory) / "connections.json",
                manifests,
            )
            connections.create(
                connection_id="echo",
                connector_id="generic-acp",
                display_name="Echo",
                configuration={
                    "command": sys.executable,
                    "arguments": ["-m", "tests.fake_acp_agent"],
                    "sessionId": "session-1",
                    "workingDirectory": str(Path.cwd()),
                },
            )
            executor = PlatformConnectionExecutor(
                connections,
                manifests,
                BuiltinLifecycleRegistry(),
            )

            async with executor.execute("echo") as execution:
                events = [
                    event
                    async for event in execution.session.prompt(
                        execution.agent_session_id,
                        "hello",
                    )
                ]

        self.assertEqual(
            [(event.kind, event.text) for event in events],
            [("text_delta", "echo:hello"), ("completed", "")],
        )


if __name__ == "__main__":
    unittest.main()
