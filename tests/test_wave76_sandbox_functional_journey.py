import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_wave76_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave76SandboxFunctionalJourneyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_empty_and_initial_sandbox_are_honest(self):
        empty = self.runtime.uat_sandbox_journey()
        self.assertEqual(empty["schema"], "binario.marketing.uat-sandbox-journey.v1")
        self.assertEqual(empty["summary"]["core_required"], 0)
        self.assertFalse(empty["summary"]["core_complete"])

        sandbox = self.runtime.create_uat_sandbox({})
        journey = self.runtime.uat_sandbox_journey()
        self.assertEqual(journey["summary"]["core_required"], 6)
        self.assertEqual(journey["summary"]["core_verified"], 2)
        self.assertFalse(journey["summary"]["core_complete"])
        self.assertEqual(journey["next_checkpoint"]["code"], "EXACT_MATCH_HANDOFF")
        by_code = {row["code"]: row for row in journey["checkpoints"]}
        self.assertEqual(by_code["FIXTURE_INTEGRITY"]["status"], "VERIFIED")
        self.assertEqual(by_code["CAMPAIGN_CONTEXT"]["status"], "VERIFIED")
        self.assertEqual(by_code["EXACT_MATCH_HANDOFF"]["status"], "READY_TO_TEST")
        self.assertEqual(by_code["NEW_LEAD_HANDOFF"]["status"], "READY_TO_TEST")
        self.assertEqual(by_code["RESULTS_EVIDENCE"]["status"], "EXTERNAL_OPTIONAL")
        self.assertFalse(journey["contracts"]["physical_release_evidence_allowed"])
        self.assertFalse(journey["safety"]["provider_read_performed"])
        self.assertEqual(self.runtime.physical_uat.list(sandbox["company"]["id"]), [])

    def test_observer_detects_only_operator_state_changes(self):
        sandbox = self.runtime.create_uat_sandbox({})
        cid = sandbox["company"]["id"]
        entities = sandbox["entities"]
        contact_id = entities["contact_id"]

        self.runtime.convert_lead(cid, entities["matched_lead_id"], {
            "action": "LINK_CONTACT",
            "contact_id": contact_id,
        })
        journey = self.runtime.uat_sandbox_journey()
        self.assertEqual(journey["summary"]["core_verified"], 3)
        self.assertEqual(journey["next_checkpoint"]["code"], "NEW_LEAD_HANDOFF")

        self.runtime.convert_lead(cid, entities["new_lead_id"], {"action": "CREATE_CONTACT"})
        self.runtime.crm.update_opportunity(cid, entities["opportunity_id"], {"stage": "INTERESTED"})
        self.runtime.crm.complete_activity(cid, entities["activity_id"])
        final = self.runtime.uat_sandbox_journey()
        self.assertTrue(final["summary"]["core_complete"], final)
        self.assertEqual(final["summary"]["core_verified"], 6)
        by_code = {row["code"]: row for row in final["checkpoints"]}
        for code in (
            "EXACT_MATCH_HANDOFF",
            "NEW_LEAD_HANDOFF",
            "PIPELINE_STAGE_SAVE",
            "FOLLOWUP_INTERACTION",
        ):
            self.assertEqual(by_code[code]["status"], "VERIFIED", code)
        self.assertEqual(self.runtime.physical_uat.list(cid), [])

    def test_real_company_never_becomes_the_observed_sandbox(self):
        real = self.runtime.create_company({"name": "Empresa real aislada"})
        sandbox = self.runtime.create_uat_sandbox({})
        journey = self.runtime.uat_sandbox_journey()
        self.assertNotEqual(real["id"], sandbox["company"]["id"])
        self.assertEqual(journey["sandbox"]["company"]["id"], sandbox["company"]["id"])
        self.assertTrue(self.runtime.companies.get(real["id"]).active)
        self.runtime.reset_uat_sandbox({"confirm": True})
        self.assertTrue(self.runtime.companies.get(real["id"]).active)

    def test_http_projection_and_browser_layer_are_read_only(self):
        self.runtime.create_uat_sandbox({})
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base + "/api/uat-sandbox/journey", timeout=10) as response:
                payload = json.loads(response.read())
            self.assertEqual(payload["schema"], "binario.marketing.uat-sandbox-journey.v1")
            self.assertTrue(payload["safety"]["read_only_projection"])
            with urlopen(base + "/uat-sandbox.js", timeout=10) as response:
                parent = response.read().decode()
            self.assertIn("/uat-functional-journey.js", parent)
            with urlopen(base + "/uat-functional-journey.js", timeout=10) as response:
                ui = response.read().decode()
            self.assertIn("FUNCTIONAL JOURNEY VALIDATOR · W76", ui)
            self.assertIn("Verificar cambios", ui)
            self.assertNotIn("setInterval", ui)
            self.assertNotIn("/api/meta/", ui)
            self.assertNotIn("/ai/generate", ui)
            self.assertNotIn("method:'POST'", ui)
            self.assertNotIn("method:'PATCH'", ui)
            self.assertNotIn("method:'DELETE'", ui)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_release_workflow_and_current_builder_boundaries(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('0.9.0.dev1', version)
        self.assertIn('RELEASE_READY = False', version)
        self.assertIn('RELEASE_TAG: str | None = None', version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src/binario_marketing/service_wave76_app.py").read_text(encoding="utf-8")
        self.assertNotIn("RELEASE_READY = True", service)
        self.assertNotIn("social_inbox(", service)
        self.assertNotIn("publish_company_publication_now", service)
        builder = (ROOT / "scripts/build_full_mac_current.sh").read_text(encoding="utf-8")
        for wave in range(66, 76):
            self.assertIn(f"Wave {wave}", builder)
        self.assertIn("service_wave76_app import serve", builder)


if __name__ == "__main__":
    unittest.main()
