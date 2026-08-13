import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetaConnectionUiContractTests(unittest.TestCase):
    def test_connection_ui_never_persists_or_echoes_token(self):
        js = (ROOT / 'web' / 'social.js').read_text(encoding='utf-8')
        for token in (
            'meta-connect-form',
            'meta-token-input',
            'type="password"',
            '/api/meta/connection',
            "method:'DELETE'",
            'credential_writable',
            'credential_source',
            "input.value=''",
            'Keychain',
        ):
            self.assertIn(token, js)
        self.assertNotIn('localStorage', js)
        self.assertNotIn('sessionStorage', js)

    def test_paid_media_ui_builds_full_paused_hierarchy_and_can_resume(self):
        js = (ROOT / 'web' / 'social.js').read_text(encoding='utf-8')
        for token in (
            'Campaña + Ad Set + Creative + Ad',
            '/paid-media',
            '/create-paused',
            'REMOTE_PAUSED',
            'Reanudar creación PAUSED',
            'Crear campaña pausada completa',
            'Cancelar borrador',
            'meta-daily-budget',
            'meta-target-countries',
            'meta-ad-picture',
        ):
            self.assertIn(token, js)
        self.assertNotIn('Activar campaña', js)
        self.assertNotIn("status:'ACTIVE'", js)

    def test_service_extension_keeps_legacy_core_separate(self):
        service = (ROOT / 'src' / 'binario_marketing' / 'service.py').read_text(encoding='utf-8')
        core = (ROOT / 'src' / 'binario_marketing' / 'service_core.py').read_text(encoding='utf-8')
        self.assertIn('from . import service_core as core', service)
        self.assertIn('class MarketingHandler(core.MarketingHandler)', service)
        self.assertIn('["api", "meta", "connection"]', service)
        self.assertIn('"paid-media"', service)
        self.assertIn('class MarketingHandler(BaseHTTPRequestHandler)', core)
        self.assertNotIn('["api", "meta", "connection"]', core)


if __name__ == '__main__':
    unittest.main()
