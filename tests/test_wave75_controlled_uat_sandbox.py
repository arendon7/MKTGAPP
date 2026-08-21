import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.service_wave75_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave75ControlledUATSandboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_fixture_is_synthetic_local_and_operationally_useful(self):
        status = self.runtime.create_uat_sandbox({})
        self.assertTrue(status["functional_ready"], status)
        self.assertTrue(status["active"])
        self.assertFalse(status["contract"]["physical_release_evidence_allowed"])
        self.assertFalse(status["contract"]["provider_evidence_seeded"])
        self.assertFalse(status["contract"]["results_evidence_seeded"])

        company_id = status["company"]["id"]
        company = self.runtime.companies.get(company_id)
        self.assertTrue(company.active)
        self.assertIsNone(company.facebook_page_id)
        self.assertIsNone(company.instagram_id)
        self.assertIsNone(company.ad_account_id)

        contacts = self.runtime.crm.list_contacts(company_id)
        self.assertEqual(len(contacts), 1)
        self.assertTrue(contacts[0].email.endswith("@binario.invalid"))
        self.assertIn("uat-sandbox", contacts[0].tags)

        intake = self.runtime.lead_intake_payload(company_id)
        by_id = {row["id"]: row for row in intake["leads"]}
        self.assertEqual(by_id[status["entities"]["matched_lead_id"]]["status"], "MATCHED")
        self.assertEqual(by_id[status["entities"]["matched_lead_id"]]["exact_match_count"], 1)
        self.assertEqual(by_id[status["entities"]["new_lead_id"]]["status"], "NEW")
        self.assertTrue(by_id[status["entities"]["new_lead_id"]]["email"].endswith("@binario.invalid"))

        opportunities = self.runtime.crm.list_opportunities(company_id)
        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].stage, "PROPOSAL")
        self.assertEqual(opportunities[0].currency, "COP")
        activities = self.runtime.crm.list_activities(company_id)
        self.assertEqual(len(activities), 1)
        self.assertEqual(activities[0].opportunity_id, opportunities[0].id)
        campaigns = self.runtime.campaigns.list(company_id)
        self.assertEqual(len(campaigns), 1)
        self.assertEqual(campaigns[0].status, "IN_PROGRESS")
        self.assertEqual(campaigns[0].objective, "LEADS")
        self.assertEqual(campaigns[0].publication_ids, ())
        self.assertEqual(campaigns[0].media_ids, ())
        self.assertEqual(set(campaigns[0].channels), {"email", "whatsapp"})

        results = self.runtime.results_intelligence_workspace(company_id)
        self.assertIsNone(results["latest_snapshot"])
        self.assertEqual(results["summary"]["with_observed_evidence"], 0)
        self.assertEqual(results["summary"]["with_attributed_opportunities"], 0)
        self.assertEqual(results["summary"]["with_ai_analysis"], 0)
        self.assertFalse(results["safety"]["provider_read_performed"])

    def test_create_is_idempotent_and_reset_only_deactivates_recorded_sandbox(self):
        real = self.runtime.create_company({"name": "Empresa real UAT"})
        first = self.runtime.create_uat_sandbox({})
        same = self.runtime.create_uat_sandbox({})
        self.assertEqual(first["company"]["id"], same["company"]["id"])
        self.assertEqual(first["generation"], same["generation"])

        reset = self.runtime.reset_uat_sandbox({"confirm": True})
        self.assertNotEqual(first["company"]["id"], reset["company"]["id"])
        self.assertEqual(reset["generation"], first["generation"] + 1)
        self.assertFalse(self.runtime.companies.get(first["company"]["id"]).active)
        self.assertTrue(self.runtime.companies.get(reset["company"]["id"]).active)
        self.assertTrue(self.runtime.companies.get(real["id"]).active)
        self.assertTrue(self.runtime.uat_sandbox.is_sandbox(first["company"]["id"]))
        self.assertTrue(self.runtime.uat_sandbox.is_sandbox(reset["company"]["id"]))
        with self.assertRaises(ValueError):
            self.runtime.reset_uat_sandbox({"confirm": False})

    def test_sandbox_can_never_record_physical_release_evidence(self):
        sandbox = self.runtime.create_uat_sandbox({})
        with self.assertRaisesRegex(ValueError, "functional-only"):
            self.runtime.start_physical_uat(sandbox["company"]["id"], {"operator": "QA"})
        self.assertEqual(self.runtime.physical_uat.list(sandbox["company"]["id"]), [])

        real = self.runtime.create_company({"name": "Empresa física real"})
        session = self.runtime.start_physical_uat(real["id"], {"operator": "QA"})
        self.assertEqual(session["status"], "IN_PROGRESS")
        self.assertFalse(session["physical_uat_complete"])

    def test_http_routes_are_explicit_and_ui_never_autocreates_or_polls(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base + "/api/uat-sandbox", timeout=10) as response:
                initial = json.loads(response.read()); self.assertFalse(initial["exists"])
            request = Request(base + "/api/uat-sandbox", data=b"{}", headers={"Content-Type":"application/json"}, method="POST")
            with urlopen(request, timeout=10) as response:
                created = json.loads(response.read()); self.assertEqual(response.status, 201)
            request = Request(base + "/api/uat-sandbox/reset", data=b'{"confirm":true}', headers={"Content-Type":"application/json"}, method="POST")
            with urlopen(request, timeout=10) as response:
                reset = json.loads(response.read()); self.assertEqual(response.status, 201)
            self.assertNotEqual(created["company"]["id"], reset["company"]["id"])
            with urlopen(base + "/interaction-audit.js", timeout=10) as response:
                audit = response.read().decode()
            self.assertIn("/uat-sandbox.js", audit)
            with urlopen(base + "/uat-sandbox.js", timeout=10) as response:
                ui = response.read().decode()
            self.assertIn("SINTÉTICO · NO RELEASE", ui)
            self.assertIn("window.confirm", ui)
            self.assertNotIn("setInterval", ui)
            self.assertNotIn("/api/meta/", ui)
            self.assertNotIn("/ai/generate", ui)
            self.assertNotIn("publish", ui.lower())
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_release_contract_workflows_and_builder_stay_fail_closed(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('0.9.0.dev1', version)
        self.assertIn('RELEASE_READY = False', version)
        self.assertIn('RELEASE_TAG: str | None = None', version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src/binario_marketing/service_wave75_app.py").read_text(encoding="utf-8")
        self.assertNotIn("RELEASE_READY = True", service)
        self.assertNotIn("social_inbox(", service)
        self.assertNotIn("publish_company_publication_now", service)
        builder = (ROOT / "scripts/build_full_mac_current.sh").read_text(encoding="utf-8")
        for wave in range(66, 75):
            self.assertIn(f"Wave {wave}", builder)
        self.assertIn("service_wave74_app import serve", builder)


if __name__ == "__main__":
    unittest.main()
