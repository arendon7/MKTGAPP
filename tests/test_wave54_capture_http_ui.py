import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave54_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave54CaptureHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Campaña W54", "objective": "LEADS", "status": "IN_PROGRESS"
        })
        self.link = self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": self.campaign["id"],
            "destination_url": "https://example.com/form",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
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

    def capture_payload(self):
        return {
            "bm_tid": self.link["tracking_code"],
            "utm_source": self.link["utm_source"],
            "utm_medium": self.link["utm_medium"],
            "utm_campaign": self.link["utm_campaign"],
            "utm_id": self.link["utm_id"],
            "utm_source_platform": self.link["utm_source_platform"],
            "landing_url": "https://example.com/form?email=not-stored@example.com",
            "bridge_version": "1.0.0",
        }

    def test_ui_portable_bundle_and_capture_contract_are_served(self):
        with urlopen(self.base + "/capture-bridge.js", timeout=5) as response:
            ui = response.read().decode("utf-8")
        with urlopen(self.base + "/first-party-capture-bridge.js", timeout=5) as response:
            portable = response.read().decode("utf-8")
        self.assertIn("Capture Bridge", ui)
        self.assertIn("Descargar JS portable", ui)
        self.assertIn("sessionStorage", portable)
        self.assertIn("MutationObserver", portable)
        status, payload = self.request_json(f"/api/companies/{self.company['id']}/attribution/capture-bridge")
        self.assertEqual(status, 200)
        self.assertEqual(payload["schema"], "binario.marketing.first-party-capture-bridge.v1")
        self.assertFalse(payload["form_contract"]["network_calls"])
        self.assertTrue(payload["evidence_contract"]["server_received_at_authoritative"])
        self.assertFalse(payload["evidence_contract"]["full_form_body_persisted"])

    def test_existing_contact_post_accepts_nested_capture_and_creates_evidence(self):
        status, contact = self.request_json(
            f"/api/companies/{self.company['id']}/contacts",
            method="POST",
            body={
                "name": "Lead W54",
                "email": "lead@example.com",
                "attribution_capture": self.capture_payload(),
            },
        )
        self.assertEqual(status, 201)
        status, bridge = self.request_json(f"/api/companies/{self.company['id']}/attribution/capture-bridge")
        self.assertEqual(status, 200)
        self.assertEqual(bridge["summary"]["capture_records"], 1)
        self.assertEqual(bridge["captures"][0]["contact_id"], contact["id"])
        self.assertNotIn("lead@example.com", json.dumps(bridge))
        self.assertNotIn("not-stored@example.com", json.dumps(bridge))

    def test_direct_capture_import_is_explicit_and_company_scoped(self):
        contact = self.runtime.create_contact(self.company["id"], {"name": "Existing"})
        status, result = self.request_json(
            f"/api/companies/{self.company['id']}/attribution/captures",
            method="POST",
            body={**self.capture_payload(), "contact_id": contact["id"]},
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["capture"]["source"], "API_IMPORT")
        self.assertEqual(result["claim"]["contact_id"], contact["id"])
        status, attribution = self.request_json(f"/api/companies/{self.company['id']}/attribution")
        self.assertEqual(status, 200)
        self.assertEqual(attribution["capture_bridge"]["summary"]["capture_records"], 1)
        self.assertEqual(attribution["summary"]["attributed_contacts"], 1)

    def test_tampered_utm_returns_400_and_does_not_create_contact(self):
        body = self.capture_payload()
        body["utm_source"] = "tampered"
        request = Request(
            self.base + f"/api/companies/{self.company['id']}/contacts",
            method="POST",
            data=json.dumps({"name": "No crear", "attribution_capture": body}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(HTTPError) as ctx:
            urlopen(request, timeout=5)
        self.assertEqual(ctx.exception.code, 400)
        self.assertEqual(len(self.runtime.crm.list_contacts(self.company["id"])), 0)

    def test_portable_bridge_has_no_network_submit_or_polling_capability(self):
        portable = (ROOT / "web" / "first-party-capture-bridge.js").read_text(encoding="utf-8")
        ui = (ROOT / "web" / "capture-bridge.js").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave54_app.py").read_text(encoding="utf-8")
        for forbidden in ("fetch(", "XMLHttpRequest", "sendBeacon", "requestSubmit", ".submit(", "setInterval"):
            self.assertNotIn(forbidden, portable)
        self.assertIn("sessionStorage", portable)
        self.assertIn("MutationObserver", portable)
        self.assertIn("bm_tid", portable)
        self.assertNotIn("setInterval", ui)
        self.assertIn('"server_received_at_authoritative": True', service)
        self.assertIn('"client_timestamp_authoritative": False', service)
        self.assertIn('"clicks_observed": False', service)
        self.assertIn('"temporal_inference": False', service)

    def test_loader_and_current_builder_chain_wave54_without_losing_prior_contracts(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_wave54_capture_bridge.sh").read_text(encoding="utf-8")
        self.assertIn("attribution.addEventListener('load',loadCaptureBridge", loader)
        self.assertIn("capture.src='/capture-bridge.js'", loader)
        self.assertIn("service_wave53_app','service_wave54_app", builder)
        self.assertIn("audit_wave54_capture_bridge.sh", builder)
        self.assertIn("Wave 52", builder)
        self.assertIn("Wave 53", builder)
        self.assertIn("Wave 54", builder)
        self.assertNotIn(".github/workflows", audit)


if __name__ == "__main__":
    unittest.main()
