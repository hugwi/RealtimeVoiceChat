import json
import stat
import tempfile
import unittest
from pathlib import Path

from vocis.connections import (
    PlatformConnectionError,
    PlatformConnectionNotFound,
    PlatformConnectionStore,
)
from vocis.connectors import ConnectorRegistry


class PlatformConnectionStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary_directory.name) / "connections.json"
        self.store = PlatformConnectionStore(
            self.path, ConnectorRegistry.discover()
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_create_persist_list_update_and_delete(self) -> None:
        created = self.store.create(
            connection_id="remote-omnigent",
            connector_id="omnigent",
            display_name="Remote OmniGent",
            configuration={"serverUrl": "https://agent.example.test"},
            credential_grant_id="grant-123",
        )

        reloaded = PlatformConnectionStore(
            self.path, ConnectorRegistry.discover()
        )
        self.assertEqual(reloaded.get(created.id), created)
        self.assertEqual(reloaded.list(), (created,))
        self.assertEqual(
            stat.S_IMODE(self.path.stat().st_mode),
            0o600,
        )

        updated = reloaded.update(
            created.id,
            display_name="Home OmniGent",
            configuration={
                "serverUrl": "https://new.example.test",
                "projectDirectory": "/workspace",
            },
            credential_grant_id="grant-456",
        )
        self.assertEqual(updated.id, created.id)
        self.assertEqual(updated.created_at, created.created_at)
        self.assertEqual(updated.display_name, "Home OmniGent")
        self.assertEqual(updated.credential_grant_id, "grant-456")

        renamed = reloaded.update(created.id, display_name="Renamed OmniGent")
        self.assertEqual(
            dict(renamed.configuration),
            {
                "serverUrl": "https://new.example.test",
                "projectDirectory": "/workspace",
            },
        )

        reloaded.delete(created.id)
        self.assertEqual(reloaded.list(), ())
        with self.assertRaises(PlatformConnectionNotFound):
            reloaded.get(created.id)

    def test_generated_id_is_stable_across_reload(self) -> None:
        created = self.store.create(
            connector_id="omnigent",
            display_name="OmniGent",
            configuration={"serverUrl": "http://localhost:3000"},
            credential_grant_id="local-grant",
        )
        reloaded = PlatformConnectionStore(
            self.path, ConnectorRegistry.discover()
        ).get(created.id)
        self.assertEqual(reloaded.id, created.id)

    def test_configuration_is_validated_against_manifest(self) -> None:
        invalid_configurations = (
            {},
            {"serverUrl": "not a URI"},
            {"serverUrl": "https://example.test", "unexpected": True},
            {"serverUrl": 42},
        )
        for configuration in invalid_configurations:
            with self.subTest(configuration=configuration):
                with self.assertRaises(PlatformConnectionError):
                    self.store.create(
                        connector_id="omnigent",
                        display_name="OmniGent",
                        configuration=configuration,
                        credential_grant_id="grant",
                    )

    def test_secrets_are_rejected_and_never_serialized(self) -> None:
        secret = "must-not-reach-disk"
        with self.assertRaisesRegex(
            PlatformConnectionError, "Credential Grant"
        ):
            self.store.create(
                connector_id="omnigent",
                display_name="OmniGent",
                configuration={
                    "serverUrl": "https://example.test",
                    "token": secret,
                },
                credential_grant_id="grant",
            )

        self.assertFalse(self.path.exists())
        self.assertNotIn(
            secret,
            self.path.read_text(encoding="utf-8") if self.path.exists() else "",
        )

    def test_duplicate_and_unknown_ids_have_clear_errors(self) -> None:
        arguments = {
            "connection_id": "duplicate",
            "connector_id": "omnigent",
            "display_name": "OmniGent",
            "configuration": {"serverUrl": "https://example.test"},
            "credential_grant_id": "grant",
        }
        self.store.create(**arguments)
        with self.assertRaisesRegex(PlatformConnectionError, "already exists"):
            self.store.create(**arguments)
        with self.assertRaises(PlatformConnectionNotFound):
            self.store.delete("missing")

    def test_store_contains_reference_but_no_credential_material(self) -> None:
        self.store.create(
            connector_id="omnigent",
            display_name="OmniGent",
            configuration={"serverUrl": "https://example.test"},
            credential_grant_id="grant-reference",
        )
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        record = raw["connections"][0]
        self.assertEqual(record["credentialGrantId"], "grant-reference")
        self.assertNotIn("credential", record["configuration"])
        self.assertNotIn("token", self.path.read_text(encoding="utf-8").lower())

    def test_rejects_invalid_identity_loaded_from_disk(self) -> None:
        self.store.create(
            connection_id="valid",
            connector_id="omnigent",
            display_name="OmniGent",
            configuration={"serverUrl": "https://example.test"},
            credential_grant_id="grant-reference",
        )
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        raw["connections"][0]["id"] = "../escape"
        self.path.write_text(json.dumps(raw), encoding="utf-8")

        with self.assertRaisesRegex(
            PlatformConnectionError, "connection id"
        ):
            self.store.list()

    def test_authless_connector_does_not_invent_credential_grant(self) -> None:
        created = self.store.create(
            connection_id="local-acp",
            connector_id="generic-acp",
            display_name="Local ACP",
            configuration={
                "command": "example-acp-agent",
                "sessionId": "session-1",
            },
        )

        self.assertIsNone(created.credential_grant_id)
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertIsNone(raw["connections"][0]["credentialGrantId"])


if __name__ == "__main__":
    unittest.main()
