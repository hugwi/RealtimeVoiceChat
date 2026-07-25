from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from vocis.connectors import ConnectorManifestError, ConnectorRegistry


class ConnectorRegistryTests(unittest.TestCase):
    def test_discovers_validated_builtin_omnigent_manifest(self) -> None:
        registry = ConnectorRegistry.discover()

        manifest = registry.require("omnigent")

        self.assertEqual(manifest.display_name, "OmniGent")
        self.assertEqual(manifest.protocol, "acp")
        self.assertEqual(manifest.protocol_version, 1)
        self.assertTrue(manifest.supports("streamingText"))
        self.assertTrue(manifest.supports("permissions"))
        self.assertFalse(manifest.supports("sessionDiscovery"))
        self.assertEqual(manifest.preferred_authentication, "oauth-device")

    def test_rejects_duplicate_connector_ids(self) -> None:
        builtin = ConnectorRegistry.discover().require("omnigent")

        with self.assertRaisesRegex(ConnectorManifestError, "duplicate connector id"):
            ConnectorRegistry([builtin, builtin])

    def test_rejects_unknown_manifest_fields(self) -> None:
        source = Path(__file__).parents[1] / "vocis/connectors/builtin/omnigent.connector.json"
        payload = json.loads(source.read_text(encoding="utf-8"))
        payload["runtime"]["shell"] = True
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.connector.json"
            path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ConnectorManifestError, "unknown shell"):
                ConnectorRegistry.discover([directory])
