import os
import unittest
from unittest.mock import patch

from binario_marketing.providers import diagnose_provider


class ProviderTests(unittest.TestCase):
    def test_missing_key_is_explained_without_secret_storage(self):
        with patch.dict(os.environ, {}, clear=True):
            result = diagnose_provider("openai")
            self.assertFalse(result["configured"])
            self.assertIn("OPENAI_API_KEY", result["missing"])
            self.assertNotIn("value", result)

    def test_local_provider_needs_no_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = diagnose_provider("ollama")
            self.assertTrue(result["configured"])
            self.assertTrue(result["local"])


if __name__ == "__main__":
    unittest.main()
