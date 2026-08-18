import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave53_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave53AttributionHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.contact = self.runtime.create_contact(self.company["id"], {"name": "Lead"})
        self.opportunity = self.runtime.create_opportunity(self.company["id"], {
            "contact_id": self.contact["id"],
            "title": "Oportunidad W53",
            "stage": "WON",
            "value": 990000,
            "currency": "COP",
        })
        self.campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Campaña W53", "objective": "LEADS", "status": "IN_PROGRESS"
        })
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

    def request_json(self, path, *, method="GET", body=None):
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = Request(
            self.base + path,
            method=method,
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
        )
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_bundle_and_local_attribution_get_are_served(self):
        with urlopen(self.base + "/attribution-foundation.js", timeout=5) as response:
            text = response.read().decode("utf-8")
        self.assertIn("Attribution Foundation", text)
        self.assertIn("Crear enlace con UTM + bm_tid", text)
        self.assertIn("Vincular bm_tid capturado", text)
        self.assertIn("Generar el enlace no registra un clic", text)
        status, payload = self.request_json(f"/api/companies/{self.company['id']}/attribution")
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema"], "binario.marketing.attribution-foundation.v1")
        self.assertFalse(payload["model"]["clicks_observed"])
        self.assertFalse(payload["model"]["temporal_inference"])
        self.assertEqual(payload["model"]["opportunity_credit"], "LAST_CAPTURED_TOUCH")
        self.assertFalse(payload["safety"]["provider_call_performed"])

    def test_http_link_and_captured_claim_roundtrip(self):
        status, link = self.request_json(
            f"/api/companies/{self.company['id']}/attribution/links",
            method="POST",
            body={
                "campaign_id": self.campaign["id"],
                "destination_url": "https://example.com/w53",
                "utm_source": "instagram",
                "utm_medium": "paid_social",
            },
        )
        self.assertEqual(status, 201)
        self.assertRegex(link["tracking_code"], r"^bm_[0-9a-f]{24}$")
        self.assertIn("utm_id=campaign_", link["tracked_url"])
        self.assertIn("bm_tid=bm_", link["tracked_url"])

        status, claim = self.request_json(
            f"/api/companies/{self.company['id']}/attribution/claims",
            method="POST",
            body={
                "tracking_code": link["tracking_code"],
                "opportunity_id": self.opportunity["id"],
                "evidence": "CAPTURED_TRACKING_CODE",
            },
        )
        self.assertEqual(status, 201)
        self.assertEqual(claim["evidence"], "CAPTURED_TRACKING_CODE")
        self.assertEqual(claim["opportunity_id"], self.opportunity["id"])

        status, payload = self.request_json(f"/api/companies/{self.company['id']}/attribution")
        self.assertEqual(status, 200)
        self.assertEqual(payload["summary"]["tracking_links"], 1)
        self.assertEqual(payload["summary"]["captured_touches"], 1)
        self.assertEqual(payload["summary"]["attributed_opportunities"], 1)
        self.assertEqual(payload["summary"]["attributed_won"], 1)
        self.assertEqual(payload["summary"]["value_by_currency"]["COP"]["won_value"], 990000)

    def test_ui_has_no_click_collector_polling_or_provider_execution(self):
        ui = (ROOT / "web" / "attribution-foundation.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave53_app.py").read_text(encoding="utf-8")
        store = (ROOT / "src" / "binario_marketing" / "attribution_store.py").read_text(encoding="utf-8")
        self.assertNotIn("setInterval", ui)
        self.assertNotIn("/click", ui)
        self.assertNotIn("window.location", ui)
        self.assertNotIn("fetch('https://", ui)
        self.assertIn('"clicks_observed": False', service)
        self.assertIn('"temporal_inference": False', service)
        self.assertIn('"provider_call_performed": False', service)
        self.assertIn("Creating a TrackingLink is instrumentation only", store)
        self.assertIn("never infers attribution from dates", store)

    def test_loader_and_current_arm64_builder_chain_wave53_after_wave52(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_wave53_attribution_foundation.sh").read_text(encoding="utf-8")
        self.assertIn("learning.addEventListener('load',loadAttribution", loader)
        self.assertIn("attribution.src='/attribution-foundation.js'", loader)
        self.assertIn("service_wave52_app','service_wave53_app", builder)
        self.assertIn("audit_wave53_attribution_foundation.sh", builder)
        self.assertIn("Wave 53", builder)
        self.assertIn("LAST_CAPTURED_TOUCH", audit)
        self.assertNotIn(".github/workflows", audit)


if __name__ == "__main__":
    unittest.main()
