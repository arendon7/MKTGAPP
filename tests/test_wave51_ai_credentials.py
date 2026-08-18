import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.ai_credentials import AICredentialError, AICredentialStore


class Wave51AICredentialTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / "state"
        self.state.mkdir()
        self.helper = root / "keychain-helper"
        self.helper.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            f"ROOT='{self.state}'\n"
            "CMD=${1:-status}\n"
            "PROVIDER=${2:-meta}\n"
            "case \"$PROVIDER\" in meta|openai|anthropic|gemini) ;; *) exit 2 ;; esac\n"
            "FILE=\"$ROOT/$PROVIDER\"\n"
            "case \"$CMD\" in\n"
            "  get) [ -f \"$FILE\" ] || exit 3; cat \"$FILE\" ;;\n"
            "  set) cat > \"$FILE\"; echo ok ;;\n"
            "  delete) rm -f \"$FILE\"; echo ok ;;\n"
            "  status) [ -f \"$FILE\" ] && echo configured || echo missing ;;\n"
            "  *) exit 64 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        self.helper.chmod(0o755)
        self.store = AICredentialStore(self.helper)

    def tearDown(self):
        self.tmp.cleanup()

    def test_cloud_provider_namespaces_are_separate(self):
        self.store.write("openai", "sk-openai")
        self.store.write("anthropic", "sk-anthropic")
        self.assertEqual(self.store.read("openai"), "sk-openai")
        self.assertEqual(self.store.read("anthropic"), "sk-anthropic")
        self.assertIsNone(self.store.read("gemini"))
        self.assertTrue(self.store.status("openai").configured)
        self.assertTrue(self.store.status("anthropic").configured)
        self.assertFalse(self.store.status("gemini").configured)
        self.store.delete("openai")
        self.assertIsNone(self.store.read("openai"))
        self.assertEqual(self.store.read("anthropic"), "sk-anthropic")

    def test_environment_key_has_precedence_and_cannot_be_mutated(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "env-key"}, clear=False):
            status = self.store.status("openai")
            self.assertTrue(status.configured)
            self.assertEqual(status.source, "environment")
            self.assertEqual(self.store.read("openai"), "env-key")
            with self.assertRaisesRegex(AICredentialError, "controlled"):
                self.store.write("openai", "other")
            with self.assertRaisesRegex(AICredentialError, "environment"):
                self.store.delete("openai")

    def test_ollama_never_requires_or_persists_a_secret(self):
        status = self.store.status("ollama")
        self.assertTrue(status.configured)
        self.assertTrue(status.local)
        self.assertEqual(status.source, "local")
        self.assertIsNone(self.store.read("ollama"))
        with self.assertRaisesRegex(AICredentialError, "does not need"):
            self.store.write("ollama", "secret")

    def test_invalid_provider_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported"):
            self.store.status("unknown")

    def test_native_swift_helper_keeps_meta_compatibility_and_named_ai_slots(self):
        source = (Path(__file__).resolve().parents[1] / "native" / "meta_keychain_helper.swift").read_text(encoding="utf-8")
        self.assertIn('arguments.count > 1 ? arguments[1].lowercased() : "meta"', source)
        for provider in ("meta", "openai", "anthropic", "gemini"):
            self.assertIn(f'"{provider}": SecretSlot', source)
        self.assertIn("com.sistemabinario.marketing.meta", source)
        self.assertIn("com.sistemabinario.marketing.ai.openai", source)
        self.assertNotIn("print(value)", source)


if __name__ == "__main__":
    unittest.main()
