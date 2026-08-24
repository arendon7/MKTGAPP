import json
import re
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave74_app import AppRuntime, INTERACTION_ASSETS, create_server

ROOT = Path(__file__).resolve().parents[1]
VIEWS = ("home", "campaigns", "pauta", "calendar", "publish", "video", "content", "crm", "audiences", "analytics", "inbox", "companies")


class Wave74InteractionIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _json(self, path):
        with urlopen(self.base + path, timeout=10) as response:
            return response.status, json.loads(response.read())

    def _post(self, path, payload):
        req = Request(self.base + path, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=10) as response:
            return response.status, json.loads(response.read())

    def test_probe_is_injected_before_base_app_and_audit_after_product_entry(self):
        with urlopen(self.base + "/", timeout=10) as response:
            html = response.read().decode()
        self.assertEqual(html.count('/interaction-probe.js'), 1)
        self.assertEqual(html.count('/interaction-audit.js'), 1)
        self.assertLess(html.index('/interaction-probe.js'), html.index('/app.js'))
        self.assertLess(html.index('/product-entry-wave73.js'), html.index('/interaction-audit.js'))
        for name in INTERACTION_ASSETS:
            with urlopen(self.base + "/" + name, timeout=10) as response:
                self.assertEqual(response.status, 200)
                self.assertGreater(len(response.read()), 0)

    def test_interaction_contract_is_company_scoped_and_read_only(self):
        status, initial = self._json('/api/interaction-integrity')
        self.assertEqual(status, 200)
        self.assertTrue(initial['ready'], initial['missing'])
        status, company = self._post('/api/companies', {'name': 'Wave 74 Interaction Audit'})
        self.assertEqual(status, 201)
        status, report = self._json(f"/api/interaction-integrity?company_id={company['id']}")
        self.assertEqual(status, 200)
        self.assertTrue(report['ready'], report['missing'])
        self.assertEqual(report['company']['id'], company['id'])
        self.assertEqual(tuple(report['browser_contract']['views']), VIEWS)
        self.assertFalse(report['browser_contract']['programmatic_clicks'])
        self.assertFalse(report['browser_contract']['form_submission'])
        self.assertFalse(report['browser_contract']['provider_activation'])

    def test_probe_and_browser_audit_never_execute_controls(self):
        probe = (ROOT / 'web/interaction-probe.js').read_text(encoding='utf-8')
        audit = (ROOT / 'web/interaction-audit.js').read_text(encoding='utf-8')
        self.assertIn('EventTarget.prototype.addEventListener', probe)
        self.assertIn('UNWIRED', probe)
        self.assertIn('wave74RunInteractionAudit', audit)
        self.assertIn('Auditar controles', audit)
        for view in VIEWS:
            self.assertIn(f"'{view}'", audit)
        for forbidden in ('fetch(', '.click(', '.submit(', 'setInterval'):
            self.assertNotIn(forbidden, audit)
        self.assertIn('programmaticClicks:false', audit)
        self.assertIn('submittedForms:false', audit)

    def test_static_html_action_ids_are_referenced_by_browser_code(self):
        html = (ROOT / 'web/index.html').read_text(encoding='utf-8')
        action_ids = set(re.findall(r'<(?:button|form)\b[^>]*\bid="([^"]+)"', html))
        self.assertGreater(len(action_ids), 10)
        corpus = '\n'.join(path.read_text(encoding='utf-8') for path in (ROOT / 'web').glob('*.js'))
        missing = sorted(control_id for control_id in action_ids if control_id not in corpus)
        self.assertEqual(missing, [], f'static action controls without browser reference: {missing}')

    def test_release_workflows_and_builder_remain_fail_closed(self):
        self.assertEqual(source_release_state(), PREPARED_RELEASE)
        report = source_release_readiness()
        self.assertTrue(report['source_ready'])
        self.assertFalse(report['operational_inputs_complete'])
        self.assertFalse(report['production_ready'])
        workflows = sorted(path.name for path in (ROOT / '.github/workflows').glob('*.yml'))
        self.assertEqual(workflows, ['ci.yml', 'full-mac-app.yml', 'persistent-release.yml'])
        service = (ROOT / 'src/binario_marketing/service_wave74_app.py').read_text(encoding='utf-8')
        self.assertNotIn('RELEASE_READY = True', service)
        builder = (ROOT / 'scripts/build_full_mac_current.sh').read_text(encoding='utf-8')
        self.assertIn('service_wave73_app import serve', builder)


if __name__ == '__main__':
    unittest.main()
