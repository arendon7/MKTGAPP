import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.crm_store_wave45 import CRMStoreWave45
from binario_marketing.service_post_w99_existing_activity_reschedule_control_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class PostW99ExistingActivityRescheduleControlTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def _fixture(self, runtime, *, name="Activity Owner"):
        company = runtime.create_company({"name": name})
        company_id = company["id"]
        contact = runtime.create_contact(company_id, {"name": "Contacto exacto"})
        opportunity = runtime.create_opportunity(company_id, {
            "title": "Oportunidad exacta",
            "contact_id": contact["id"],
            "stage": "PROPOSAL",
        })
        return company_id, contact, opportunity

    def _future_iso(self, *, hours=72):
        return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0).isoformat()

    def test_runtime_reuses_wave45_crm_store_and_reschedule_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                self.assertIsInstance(runtime.crm, CRMStoreWave45)
                self.assertTrue(callable(runtime.reschedule_activity))
                self.assertTrue(callable(runtime.complete_activity))
                self.assertTrue(callable(runtime.update_opportunity))
                source = (ROOT / "src" / "binario_marketing" / "service_post_w99_existing_activity_reschedule_control_app.py").read_text()
                self.assertNotIn("PostW99ActivityCRMStore", source)
                self.assertNotIn("runtime.crm =", source)
                self.assertNotIn("def do_PATCH", source)
            finally:
                self._shutdown_runtime(runtime)

    def test_wave45_reschedule_changes_existing_due_at_only_and_records_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                activity = runtime.create_activity(company_id, {
                    "contact_id": contact["id"],
                    "opportunity_id": opportunity["id"],
                    "kind": "CALL",
                    "summary": "Confirmar propuesta",
                })
                due = self._future_iso(hours=96)
                changed = runtime.reschedule_activity(company_id, activity["id"], {"due_at": due})
                self.assertEqual(changed["id"], activity["id"])
                self.assertEqual(changed["contact_id"], activity["contact_id"])
                self.assertEqual(changed["opportunity_id"], activity["opportunity_id"])
                self.assertEqual(changed["kind"], activity["kind"])
                self.assertEqual(changed["summary"], activity["summary"])
                self.assertIsNone(changed["completed_at"])
                self.assertEqual(changed["due_at"], due)
                events = [row for row in runtime.workspace.registries.timeline.entries() if row.kind == "crm.activity.rescheduled"]
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].payload["activity_id"], activity["id"])
                self.assertIsNone(events[0].payload["due_from"])
                self.assertEqual(events[0].payload["due_to"], due)
            finally:
                self._shutdown_runtime(runtime)

    def test_wave45_reschedule_rejects_extra_missing_past_and_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                activity = runtime.create_activity(company_id, {
                    "contact_id": contact["id"],
                    "opportunity_id": opportunity["id"],
                    "kind": "TASK",
                    "summary": "Pendiente",
                })
                future = self._future_iso(hours=48)
                with self.assertRaisesRegex(ValueError, "unsupported reschedule fields"):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": future, "summary": "reescribir"})
                with self.assertRaisesRegex(ValueError, "due_at is required"):
                    runtime.reschedule_activity(company_id, activity["id"], {})
                with self.assertRaises(ValueError):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": "not-a-date"})
                past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
                with self.assertRaisesRegex(ValueError, "due_at must be in the future"):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": past})
                runtime.complete_activity(company_id, activity["id"])
                with self.assertRaisesRegex(ValueError, "completed activity cannot be rescheduled"):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": future})
            finally:
                self._shutdown_runtime(runtime)

    def test_pipeline_followup_codes_use_exact_next_activity_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                activity = runtime.create_activity(company_id, {
                    "contact_id": contact["id"],
                    "opportunity_id": opportunity["id"],
                    "kind": "CALL",
                    "summary": "Seguimiento exacto",
                })
                card = next(row for lane in runtime.commercial_pipeline(company_id)["lanes"] for row in lane["opportunities"] if row["id"] == opportunity["id"])
                self.assertEqual(card["followup"]["next_activity_id"], activity["id"])
                for kind in ("pipeline_overdue_followup", "pipeline_unscheduled_followup"):
                    action = {"kind": kind, "action": {"opportunity_id": opportunity["id"]}}
                    owner = runtime._pipeline_activity_owner(company_id, action, card)
                    self.assertIsNotNone(owner)
                    self.assertEqual(owner.id, activity["id"])
            finally:
                self._shutdown_runtime(runtime)

    def test_due_soon_activity_owner_requires_unique_timestamp_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                due = self._future_iso(hours=30)
                first = runtime.create_activity(company_id, {
                    "contact_id": contact["id"], "opportunity_id": opportunity["id"],
                    "kind": "CALL", "summary": "Llamar", "due_at": due,
                })
                card = next(row for lane in runtime.commercial_pipeline(company_id)["lanes"] for row in lane["opportunities"] if row["id"] == opportunity["id"])
                action = {"kind": "pipeline_due_soon", "due_at": due, "action": {"opportunity_id": opportunity["id"]}}
                owner = runtime._pipeline_activity_owner(company_id, action, card)
                self.assertIsNotNone(owner)
                self.assertEqual(owner.id, first["id"])

                runtime.update_opportunity(company_id, opportunity["id"], {"next_action": "Enviar mensaje", "next_action_at": due})
                ambiguous_card = next(row for lane in runtime.commercial_pipeline(company_id)["lanes"] for row in lane["opportunities"] if row["id"] == opportunity["id"])
                self.assertIsNone(runtime._pipeline_activity_owner(company_id, action, ambiguous_card))

                other_company_id, other_contact, other_opportunity = self._fixture(runtime, name="Second unique test")
                due2 = self._future_iso(hours=31)
                runtime.create_activity(other_company_id, {"contact_id": other_contact["id"], "opportunity_id": other_opportunity["id"], "kind": "CALL", "summary": "Uno", "due_at": due2})
                runtime.create_activity(other_company_id, {"contact_id": other_contact["id"], "opportunity_id": other_opportunity["id"], "kind": "TASK", "summary": "Dos", "due_at": due2})
                card2 = next(row for lane in runtime.commercial_pipeline(other_company_id)["lanes"] for row in lane["opportunities"] if row["id"] == other_opportunity["id"])
                action2 = {"kind": "pipeline_due_soon", "due_at": due2, "action": {"opportunity_id": other_opportunity["id"]}}
                self.assertIsNone(runtime._pipeline_activity_owner(other_company_id, action2, card2))
            finally:
                self._shutdown_runtime(runtime)

    def test_action_center_routes_unique_activity_due_soon_without_reprioritizing(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                due = self._future_iso(hours=30)
                activity = runtime.create_activity(company_id, {
                    "contact_id": contact["id"], "opportunity_id": opportunity["id"],
                    "kind": "TASK", "summary": "Seguimiento futuro", "due_at": due,
                })
                parent = super(AppRuntime, runtime).action_center(company_id)
                payload = runtime.action_center(company_id)
                before_ids = [row["id"] for row in parent["queue"]]
                after_ids = [row["id"] for row in payload["queue"]]
                self.assertEqual(after_ids, before_ids)
                parent_row = next(row for row in parent["queue"] if row["kind"] == "pipeline_due_soon" and row["action"].get("opportunity_id") == opportunity["id"])
                row = next(row for row in payload["queue"] if row["id"] == parent_row["id"])
                self.assertEqual((row["rank"], row["urgency"]), (parent_row["rank"], parent_row["urgency"]))
                self.assertEqual(row["action"]["view"], "crm")
                self.assertEqual(row["action"]["tab"], "followups")
                self.assertEqual(row["action"]["entity_id"], activity["id"])
                self.assertEqual(row["owner_resolution"]["mutation_owner"], "WAVE45_FOLLOWUP_RESCHEDULE")
                self.assertTrue(payload["contracts"]["activity_owner_routing_does_not_reprioritize"])
                self.assertTrue(payload["contracts"]["activity_reschedule_mutation_remains_wave45_authority"])
            finally:
                self._shutdown_runtime(runtime)

    def test_http_reuses_wave45_post_reschedule_and_rejects_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company_id, contact, opportunity = self._fixture(runtime, name="Activity HTTP")
            activity = runtime.create_activity(company_id, {"contact_id": contact["id"], "opportunity_id": opportunity["id"], "kind": "CALL", "summary": "HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                due = self._future_iso(hours=120)
                body = json.dumps({"due_at": due}).encode("utf-8")
                request = Request(root + f"/api/companies/{company_id}/activities/{activity['id']}/reschedule", data=body, headers={"Content-Type": "application/json"}, method="POST")
                changed = json.loads(urlopen(request, timeout=5).read().decode("utf-8"))
                self.assertEqual(changed["id"], activity["id"])
                self.assertEqual(changed["due_at"], due)

                bad = Request(root + f"/api/companies/{company_id}/activities/{activity['id']}/reschedule", data=json.dumps({"due_at": self._future_iso(hours=144), "summary": "bad"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
                with self.assertRaises(HTTPError) as raised:urlopen(bad, timeout=5)
                self.assertEqual(raised.exception.code, 400)
            finally:
                server.shutdown();thread.join(timeout=5);server.server_close();self._shutdown_runtime(runtime)

    def test_browser_adapter_reuses_wave45_and_contains_no_business_mutation(self):
        adapter = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")
        canonical = (ROOT / "web" / "followup-reschedule.js").read_text(encoding="utf-8")
        bootstrap = (ROOT / "web" / "product-bootstrap.js").read_text(encoding="utf-8")
        for required in ("followupRescheduleOpen", "WAVE45_FOLLOWUP_RESCHEDULE", "crm-activity-owner-actions", "pipeline_unscheduled_followup", "pipeline_overdue_followup", "pipeline_due_soon", "Completar o reprogramar seguimiento"):
            self.assertIn(required, adapter)
        for forbidden in ("opsApi(", ".click(", "dispatchEvent(", "setInterval(", "sendBeacon(", "method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'"):
            self.assertNotIn(forbidden, adapter)
        self.assertIn("/reschedule", canonical)
        self.assertIn("method:'POST'", canonical)
        self.assertIn("due_at must be in the future", (ROOT / "src" / "binario_marketing" / "crm_store_wave45.py").read_text())
        self.assertIn("'/followup-reschedule.js'", bootstrap)

    def test_bootstrap_docs_and_frozen_boundary(self):
        docs = (ROOT / "docs" / "POST_W99_EXISTING_ACTIVITY_RESCHEDULE_CONTROL.md").read_text(encoding="utf-8")
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("Wave 45", docs)
        self.assertIn("POST /api/companies/{company_id}/activities/{activity_id}/reschedule", docs)
        self.assertIn("no crea un segundo endpoint", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)
        expected = "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control"
        self.assertIn(expected, dev)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data");runtime.create_company({"name": "Bootstrap"})
            server = create_server(runtime, "127.0.0.1", 0);thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                previous = urlopen(root + "/opportunity-followup-control.js", timeout=5).read().decode("utf-8")
                current = urlopen(root + "/activity-reschedule-control.js", timeout=5).read().decode("utf-8")
                canonical = urlopen(root + "/followup-reschedule.js", timeout=5).read().decode("utf-8")
                self.assertIn("/activity-reschedule-control.js", previous)
                self.assertIn("followupRescheduleOpen", current)
                self.assertIn("/reschedule", canonical)
            finally:
                server.shutdown();thread.join(timeout=5);server.server_close();self._shutdown_runtime(runtime)


if __name__ == "__main__":
    unittest.main()
