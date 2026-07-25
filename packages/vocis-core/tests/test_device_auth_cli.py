import argparse
import io
import tempfile
import unittest
import warnings
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from vocis import __main__ as cli
from vocis.acp_sdk_agent import OfficialSdkAttachedSessionAgent
from vocis.connections import PlatformConnectionStore
from vocis.connectors import ConnectorRegistry
from vocis.credentials import DeviceAuthorization


class DeviceAuthorizationCliTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.connection_path = Path(self.temporary_directory.name) / "connections.json"
        PlatformConnectionStore(
            self.connection_path, ConnectorRegistry.discover()
        ).create(
            connection_id="remote",
            connector_id="omnigent",
            display_name="Remote OmniGent",
            configuration={"serverUrl": "https://agent.example.test"},
            credential_grant_id="remote-grant",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def arguments(self, **overrides) -> argparse.Namespace:
        values = {
            "connector": "omnigent",
            "connector_directory": [],
            "list_connectors": False,
            "connection_store": str(self.connection_path),
            "list_connections": False,
            "authorize_connection": None,
            "revoke_connection": None,
            "connection": None,
            "device_client_id": "voice-client",
            "server": "http://127.0.0.1:6767",
            "session": None,
        }
        values.update(overrides)
        return argparse.Namespace(**values)

    async def test_authorize_connection_displays_instructions_and_polls(self) -> None:
        resolver = unittest.mock.Mock()
        resolver.begin = AsyncMock(
            return_value=DeviceAuthorization(
                "https://agent.example.test/approve",
                "ABCD-EFGH",
                999,
                3,
            )
        )
        resolver.poll = AsyncMock(side_effect=[False, True])

        output = io.StringIO()
        with (
            patch.object(
                cli,
                "parse_args",
                return_value=self.arguments(authorize_connection="remote"),
            ),
            patch.object(cli, "OmnigentCredentialResolver", return_value=resolver),
            patch.object(cli.asyncio, "sleep", AsyncMock()) as sleep,
            redirect_stdout(output),
        ):
            await cli._run()

        resolver.begin.assert_awaited_once_with(
            "remote-grant",
            server_url="https://agent.example.test",
            client_id="voice-client",
        )
        self.assertEqual(resolver.poll.await_count, 2)
        sleep.assert_awaited_once_with(3)
        self.assertIn("https://agent.example.test/approve", output.getvalue())
        self.assertIn("ABCD-EFGH", output.getvalue())
        self.assertIn("authorized Credential Grant remote-grant", output.getvalue())

    async def test_revoke_connection_uses_its_grant_and_server(self) -> None:
        resolver = unittest.mock.Mock()
        resolver.revoke = AsyncMock()

        output = io.StringIO()
        with (
            patch.object(
                cli,
                "parse_args",
                return_value=self.arguments(revoke_connection="remote"),
            ),
            patch.object(cli, "OmnigentCredentialResolver", return_value=resolver),
            redirect_stdout(output),
        ):
            await cli._run()

        resolver.revoke.assert_awaited_once_with(
            "remote-grant", server_url="https://agent.example.test"
        )
        self.assertIn("revoked Credential Grant remote-grant", output.getvalue())

    async def test_authorization_rejects_non_omnigent_connection(self) -> None:
        PlatformConnectionStore(
            self.connection_path, ConnectorRegistry.discover()
        ).create(
            connection_id="local",
            connector_id="generic-acp",
            display_name="Local ACP",
            configuration={"command": "agent", "sessionId": "session-1"},
        )

        with (
            patch.object(
                cli,
                "parse_args",
                return_value=self.arguments(authorize_connection="local"),
            ),
            self.assertRaisesRegex(SystemExit, "does not use OmniGent"),
        ):
            await cli._run()

    def test_existing_list_options_still_parse(self) -> None:
        with patch("sys.argv", ["voice-bridge", "--list-connectors"]):
            self.assertTrue(cli.parse_args().list_connectors)
        with patch("sys.argv", ["voice-bridge", "--list-connections"]):
            self.assertTrue(cli.parse_args().list_connections)

    async def test_legacy_server_execution_warns_to_use_connection(self) -> None:
        backend = unittest.mock.Mock()
        backend.close = AsyncMock()
        run_agent = AsyncMock()
        arguments = self.arguments(session="conv-1")

        with (
            patch.object(cli, "parse_args", return_value=arguments),
            patch.object(cli, "OmnigentSdkBackend", return_value=backend),
            patch.dict("sys.modules", {"acp": unittest.mock.Mock(run_agent=run_agent)}),
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always")
            await cli._run()

        self.assertTrue(
            any("--server is deprecated" in str(item.message) for item in caught)
        )

    async def test_connection_execution_uses_shared_executor(self) -> None:
        session = unittest.mock.Mock()
        execution = SimpleNamespace(
            agent_session_id="conv-1",
            session=session,
        )

        class Executor:
            calls = []

            def execute(self, connection_id, agent_session_id):
                self.calls.append((connection_id, agent_session_id))

                class Context:
                    async def __aenter__(self):
                        return execution

                    async def __aexit__(self, *args):
                        return None

                return Context()

        executor = Executor()
        run_agent = AsyncMock()
        http_client = unittest.mock.Mock()
        http_client.aclose = AsyncMock()

        with (
            patch.object(
                cli,
                "parse_args",
                return_value=self.arguments(
                    connection="remote",
                    session="conv-1",
                ),
            ),
            patch.object(
                cli, "PlatformConnectionExecutor", return_value=executor
            ) as executor_type,
            patch.object(cli, "KeyringSecretStore"),
            patch("httpx.AsyncClient", return_value=http_client),
            patch.dict("sys.modules", {"acp": unittest.mock.Mock(run_agent=run_agent)}),
        ):
            await cli._run()

        self.assertEqual(executor.calls, [("remote", "conv-1")])
        agent = run_agent.await_args.args[0]
        self.assertIsInstance(agent, OfficialSdkAttachedSessionAgent)
        self.assertIs(agent._session, session)
        executor_type.assert_called_once()
        http_client.aclose.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
