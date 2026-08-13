import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetaCliContractTests(unittest.TestCase):
    def test_connect_validates_before_keychain_write_and_supports_hidden_input(self):
        source = (ROOT / 'src' / 'binario_marketing' / 'cli.py').read_text(encoding='utf-8')
        self.assertIn('getpass.getpass("Meta access token: ")', source)
        self.assertIn('MetaGraphClient(token, _meta_version()).identity()', source)
        self.assertIn('MetaCredentialStore().write(token)', source)
        self.assertLess(
            source.index('MetaGraphClient(token, _meta_version()).identity()'),
            source.index('MetaCredentialStore().write(token)'),
        )
        self.assertIn('meta-disconnect', source)
        self.assertIn('meta-status', source)

    def test_cli_never_prints_the_supplied_token(self):
        source = (ROOT / 'src' / 'binario_marketing' / 'cli.py').read_text(encoding='utf-8')
        self.assertNotIn('"token": token', source)
        self.assertNotIn("'token': token", source)
        self.assertNotIn('print(token)', source)


if __name__ == '__main__':
    unittest.main()
