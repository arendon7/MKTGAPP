import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class MetaUatContractTests(unittest.TestCase):
    def test_bundle_loads_after_social_distribution(self):
        html = (ROOT / 'web' / 'index.html').read_text(encoding='utf-8')
        self.assertIn('<script src="/social-uat.js" defer></script>', html)
        self.assertLess(html.index('/social.js'), html.index('/social-uat.js'))

    def test_uat_is_evidence_based_and_never_auto_executes_external_side_effects(self):
        js = (ROOT / 'web' / 'social-uat.js').read_text(encoding='utf-8')
        for token in (
            "row.status==='PUBLISHED'&&row.remote_id",
            "row.scheduled_for&&['QUEUED','PUBLISHING','PUBLISHED'].includes(row.status)",
            "row.status==='REMOTE_PAUSED'",
            'row.campaign_id&&row.adset_id&&row.creative_id&&row.ad_id',
            'acciones externas requieren clic explícito',
            'Publicar ahora',
            'Crear campaña pausada completa',
            'Instagram local es una capacidad adicional Wave 27',
            'este UAT mantiene Facebook Reel como gate de publicación',
        ):
            self.assertIn(token, js)
        for forbidden in (
            '/publish-now',
            '/create-paused',
            'socialPublishNow(',
            'createPaidMediaRemote(',
            'META_ACCESS_TOKEN',
        ):
            self.assertNotIn(forbidden, js)

    def test_uat_prepares_future_schedule_not_immediate_publish(self):
        js = (ROOT / 'web' / 'social-uat.js').read_text(encoding='utf-8')
        self.assertIn('Date.now()+10*60*1000', js)
        self.assertIn("$('#social-scheduled-for').value=local", js)
        self.assertIn('Guardar / programar', js)

    def test_uat_static_route_is_owned_by_wave23_extension(self):
        extension = (ROOT / 'src' / 'binario_marketing' / 'service.py').read_text(encoding='utf-8')
        core = (ROOT / 'src' / 'binario_marketing' / 'service_core.py').read_text(encoding='utf-8')
        self.assertIn('if path == "/social-uat.js":', extension)
        self.assertIn('self._static(path)', extension)
        self.assertNotIn('"/social-uat.js"', core)

    def test_full_mac_smoke_fetches_guided_uat_from_bundled_server(self):
        workflow = (ROOT / '.github' / 'workflows' / 'full-mac-app.yml').read_text(encoding='utf-8')
        self.assertIn('"$BASE/social-uat.js"', workflow)
        self.assertIn("grep -q 'metaUatReport'", workflow)

    def test_bundle_is_served_by_local_http_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / 'data')
            server = create_server(runtime, '127.0.0.1', 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                with urlopen(f"http://127.0.0.1:{server.server_address[1]}/social-uat.js", timeout=5) as response:
                    body = response.read().decode('utf-8')
                self.assertEqual(response.status, 200)
                self.assertIn('UAT META · PRUEBA GUIADA', body)
                self.assertIn('metaUatReport', body)
            finally:
                server.shutdown(); server.server_close(); thread.join(timeout=3)
                if runtime.social_scheduler is not None:
                    runtime.social_scheduler.shutdown()
                runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()


if __name__ == '__main__':
    unittest.main()
