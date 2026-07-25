from types import SimpleNamespace
import unittest

from vocis.omnigent_backend import _translate_sdk_event


class OmnigentBackendTranslationTest(unittest.TestCase):
    def test_waits_for_idle_when_native_codex_completion_precedes_text(self):
        self.assertIsNone(
            _translate_sdk_event(SimpleNamespace(type="response.completed"))
        )
        self.assertEqual(
            _translate_sdk_event(
                SimpleNamespace(type="response.output_text.delta", delta="Ready")
            ).text,
            "Ready",
        )
        self.assertEqual(
            _translate_sdk_event(
                SimpleNamespace(type="session.status", status="idle", error=None)
            ).kind,
            "completed",
        )


if __name__ == "__main__":
    unittest.main()
