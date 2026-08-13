import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class MetaDiagnosticsUiContractTests(unittest.TestCase):
    def test_uat_loads_diagnostics_after_existing_extensions(self):
        uat = (ROOT / 'web' / 'social-uat.js').read_text(encoding='utf-8')
        self.assertIn("link.href='/meta-diagnostics.css'", uat)
        self.assertIn("script.src='/meta-diagnostics.js'", uat)
        self.assertGreater(uat.index("script.src='/meta-diagnostics.js'"), uat.index("script.src='/meta-observability.js'"))

    def test_diagnostics_browser_surface_is_read_only_and_copiable(self):
        js = (ROOT / 'web' / 'meta-diagnostics.js').read_text(encoding='utf-8')
        wave25 = js.split('// Wave 26:', 1)[0]
        for required in (
            'WAVE 25 · DIAGNÓSTICO META',
            '/api/meta/diagnostics',
            'Diagnosticar acceso',
            'Copiar diagnóstico',
            'reporte sin token',
            'READ ONLY',
        ):
            self.assertIn(required, wave25)
        for forbidden in (
            "method:'POST'", 'method:"POST"', "method:'DELETE'", 'method:"DELETE"',
            '/publish-now', '/create-paused', 'META_ACCESS_TOKEN', 'access_token',
        ):
            self.assertNotIn(forbidden, wave25)

    def test_backend_route_lives_only_in_get_extension(self):
        service = (ROOT / 'src' / 'binario_marketing' / 'service.py').read_text(encoding='utf-8')
        get_block = service.split('    def do_GET(self) -> None:', 1)[1].split('    def do_POST(self) -> None:', 1)[0]
        post_block = service.split('    def do_POST(self) -> None:', 1)[1].split('    def do_DELETE(self) -> None:', 1)[0]
        delete_block = service.split('    def do_DELETE(self) -> None:', 1)[1]
        self.assertIn('["api", "meta", "diagnostics"]', get_block)
        self.assertNotIn('["api", "meta", "diagnostics"]', post_block)
        self.assertNotIn('["api", "meta", "diagnostics"]', delete_block)
        self.assertIn('if path == "/social-uat.js":', get_block)

    def test_diagnostics_styles_do_not_modify_editor_surfaces(self):
        css = (ROOT / 'web' / 'meta-diagnostics.css').read_text(encoding='utf-8')
        self.assertIn('@media(max-width:640px)', css)
        self.assertNotIn('.preview-stage{', css)
        self.assertNotIn('.timeline{', css)


if __name__ == '__main__':
    unittest.main()
