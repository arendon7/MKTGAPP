import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.meta_credentials import MetaCredentialStore
from binario_marketing.meta_graph import MetaGraphClient


ROOT = Path(__file__).resolve().parents[1]


class MetaCredentialStoreTests(unittest.TestCase):
    def _helper(self, root: str) -> Path:
        path = Path(root) / 'helper'
        path.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
        path.chmod(0o755)
        return path

    def test_environment_token_has_priority_without_persistence(self):
        with patch.dict(os.environ, {'META_ACCESS_TOKEN': 'env-secret'}, clear=True):
            store = MetaCredentialStore()
            self.assertEqual(store.read(), 'env-secret')
            status = store.status()
            self.assertTrue(status.configured)
            self.assertEqual(status.source, 'environment')

    def test_keychain_write_sends_secret_on_stdin_not_process_argv(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = self._helper(tmp)
            with patch.dict(os.environ, {}, clear=True), patch('binario_marketing.meta_credentials.subprocess.run') as run:
                run.return_value.returncode = 0
                run.return_value.stdout = 'ok\n'
                run.return_value.stderr = ''
                status = MetaCredentialStore(helper).write('super-secret-token')
            self.assertTrue(status.configured)
            args, kwargs = run.call_args
            self.assertEqual(args[0], [str(helper), 'set'])
            self.assertEqual(kwargs['input'], 'super-secret-token')
            self.assertNotIn('super-secret-token', ' '.join(args[0]))
            self.assertEqual(kwargs['env'], {'PATH': '/usr/bin:/bin'})

    def test_keychain_read_and_status_do_not_echo_secret_in_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            helper = self._helper(tmp)
            with patch.dict(os.environ, {}, clear=True), patch('binario_marketing.meta_credentials.subprocess.run') as run:
                run.side_effect = [
                    type('R', (), {'returncode': 0, 'stdout': 'configured\n', 'stderr': ''})(),
                    type('R', (), {'returncode': 0, 'stdout': 'keychain-secret', 'stderr': ''})(),
                ]
                store = MetaCredentialStore(helper)
                status = store.status()
                secret = store.read()
            self.assertEqual(status.source, 'keychain')
            self.assertTrue(status.configured)
            self.assertEqual(secret, 'keychain-secret')
            self.assertNotIn('keychain-secret', repr(status))


class NativeKeychainSourceContractTests(unittest.TestCase):
    def test_swift_helper_uses_secitem_dp_first_entitlement_fallback_and_stdin(self):
        source = (ROOT / 'native' / 'meta_keychain_helper.swift').read_text(encoding='utf-8')
        for token in (
            'SecItemCopyMatching',
            'SecItemUpdate',
            'SecItemAdd',
            'SecItemDelete',
            'kSecUseDataProtectionKeychain',
            'errSecMissingEntitlement',
            'case dataProtection',
            'case legacy',
            'FileHandle.standardInput.readDataToEndOfFile()',
        ):
            self.assertIn(token, source)
        self.assertLess(source.index('try writeSecret(clean, backend: .dataProtection)'), source.index('try writeSecret(clean, backend: .legacy)'))
        self.assertNotIn('CommandLine.arguments[2]', source)
        self.assertNotIn('write(toFile:', source)

    def test_full_mac_builder_and_audit_require_native_helper_and_provenance(self):
        builder = (ROOT / 'scripts' / 'build_full_mac_app.sh').read_text(encoding='utf-8')
        audit = (ROOT / 'scripts' / 'audit_full_mac_app.sh').read_text(encoding='utf-8')
        for token in ('meta_keychain_helper.swift', 'swiftc', 'BINARIO_META_KEYCHAIN_HELPER', 'binario-meta-keychain', 'SecItem/data-protection-first'):
            self.assertIn(token, builder)
        for token in ('BINARIO_META_KEYCHAIN_HELPER', 'binario-meta-keychain', 'MetaCredentialStore().status()', 'SecItem/data-protection-first'):
            self.assertIn(token, audit)
        self.assertIn('KEYCHAIN_STATUS="$(cd "$MACOS" && ./binario-meta-keychain status)"', audit)
        self.assertNotIn('KEYCHAIN_STATUS="$("$KEYCHAIN_HELPER" status)"', audit)
        self.assertNotIn('KEYCHAIN_STATUS="$($KEYCHAIN_HELPER status)"', audit)


class MetaGraphCredentialResolutionTests(unittest.TestCase):
    def test_graph_client_from_env_reads_credential_store(self):
        calls = []
        def transport(method, url, params):
            calls.append((method, url, dict(params)))
            return {'id': 'me-1', 'name': 'Test'}
        with patch('binario_marketing.meta_graph.MetaCredentialStore') as store_cls:
            store_cls.return_value.read.return_value = 'keychain-token'
            client = MetaGraphClient.from_env(transport=transport)
            identity = client.identity()
        self.assertEqual(identity['id'], 'me-1')
        self.assertEqual(calls[0][2]['access_token'], 'keychain-token')


if __name__ == '__main__':
    unittest.main()
