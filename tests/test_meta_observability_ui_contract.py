import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetaObservabilityUiContractTests(unittest.TestCase):
    def test_wave23_uat_loads_observability_extension_without_reordering_core_bundles(self):
        uat = (ROOT / 'web' / 'social-uat.js').read_text(encoding='utf-8')
        self.assertIn("link.href='/meta-observability.css'", uat)
        self.assertIn("script.src='/meta-observability.js'", uat)
        self.assertIn("globalThis.renderMetaUat=renderMetaUat", uat)

    def test_observability_browser_surface_is_get_only(self):
        js = (ROOT / 'web' / 'meta-observability.js').read_text(encoding='utf-8')
        for required in (
            'WAVE 24 · OBSERVABILIDAD META',
            'Sólo hace lecturas GET a Meta',
            '/observability',
            'explicit_active_detected',
            'PAUSED CONFIRMADO',
            'ALERTA ACTIVE',
        ):
            self.assertIn(required, js)
        for forbidden in (
            "method:'POST'",
            'method:"POST"',
            "method:'DELETE'",
            'method:"DELETE"',
            '/publish-now',
            '/create-paused',
            '/connection',
            'META_ACCESS_TOKEN',
        ):
            self.assertNotIn(forbidden, js)

    def test_backend_observability_routes_exist_only_under_get(self):
        service = (ROOT / 'src' / 'binario_marketing' / 'service.py').read_text(encoding='utf-8')
        get_block = service.split('    def do_GET(self) -> None:', 1)[1].split('    def do_POST(self) -> None:', 1)[0]
        post_block = service.split('    def do_POST(self) -> None:', 1)[1].split('    def do_DELETE(self) -> None:', 1)[0]
        delete_block = service.split('    def do_DELETE(self) -> None:', 1)[1]
        self.assertIn('parts[5] == "observability"', get_block)
        self.assertNotIn('observability', post_block)
        self.assertNotIn('observability', delete_block)

    def test_responsive_observability_styles_are_isolated(self):
        css = (ROOT / 'web' / 'meta-observability.css').read_text(encoding='utf-8')
        self.assertIn('.meta-observability-card', css)
        self.assertIn('@media(max-width:900px)', css)
        self.assertNotIn('.preview-stage{', css)
        self.assertNotIn('.timeline{', css)


if __name__ == '__main__':
    unittest.main()
