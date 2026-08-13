import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetaRemoteUatUiContractTests(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / 'web' / 'meta-diagnostics.js').read_text(encoding='utf-8')
        self.wave26 = self.js.split('// Wave 26:', 1)[1]

    def test_remote_uat_strengthens_existing_reel_and_paid_gates(self):
        for required in (
            'WAVE 26 · UAT REMOTO META',
            'metaRemotePatchedSteps',
            "step.id==='reel'",
            "step.id==='paid'",
            'Local PUBLISHED + Meta',
            'Local REMOTE_PAUSED + Meta PAUSED confirmado',
            'configured_paused===true',
            'explicit_active_detected',
        ):
            self.assertIn(required, self.wave26)
        self.assertIn('metaUatSteps=metaRemotePatchedSteps', self.wave26)
        self.assertIn('metaUatReport=metaRemoteUatReport', self.wave26)

    def test_remote_verification_is_get_only_and_never_recreates_objects(self):
        for required in (
            '/observability`',
            '/observability?date_preset=maximum`',
            'Verificar gates remotos',
            'no recrea objetos',
        ):
            self.assertIn(required, self.wave26)
        for forbidden in (
            "method:'POST'", 'method:"POST"', "method:'DELETE'", 'method:"DELETE"',
            '/publish-now', '/create-paused', '/connection', 'META_ACCESS_TOKEN',
        ):
            self.assertNotIn(forbidden, self.wave26)

    def test_provider_links_are_https_allowlisted_and_open_noopener(self):
        for required in (
            'metaRemoteSafeProviderUrl',
            "url.protocol==='https:'",
            "host==='facebook.com'",
            "host.endsWith('.facebook.com')",
            "host==='instagram.com'",
            "host.endsWith('.instagram.com')",
            "anchor.rel='noopener noreferrer'",
        ):
            self.assertIn(required, self.wave26)
        self.assertNotIn('window.open(', self.wave26)

    def test_meta_errors_are_normalized_and_credentials_redacted(self):
        for required in (
            "category:'TOKEN'",
            "category:'PERMISSION'",
            "category:'ASSET_ACCESS'",
            "category:'TRANSIENT'",
            "category:'VALIDATION'",
            '[credencial oculta]',
            'Bearer\\s+\\S+',
            'access_token=[credencial oculta]',
        ):
            self.assertIn(required, self.wave26)
        self.assertIn('metaRemoteSafeMessage', self.wave26)
        self.assertIn('metaRemoteExplainError', self.wave26)

    def test_remote_uat_does_not_poll_meta_automatically(self):
        self.assertIn('setInterval(()=>{if(metaRemoteProjectId())renderMetaRemoteUat()}', self.wave26)
        self.assertNotIn('setInterval(verifyMetaRemoteUat', self.wave26)
        self.assertNotIn('MutationObserver(()=>verifyMetaRemoteUat', self.wave26)


if __name__ == '__main__':
    unittest.main()
