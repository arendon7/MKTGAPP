import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.post_w99_crm_activity_store import PostW99ActivityCRMStore
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

    def test_dev_runtime_uses_narrow_post_w99_crm_store(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                self.assertIsInstance(runtime.crm, PostW99ActivityCRMStore)
                self.assertTrue(callable(runtime.reschedule_activity))
                self.assertTrue(callable(runtime.complete_activity))
                self.assertTrue(callable(runtime.update_opportunity))
            finally:
                self._shutdown_runtime(runtime)

    def test_reschedule_changes_due_at_only_and_records_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                activity = runtime.create_activity(company_id, {
                    "contact_id": contact["id"],
                    "opportunity_id": opportunity["id"],
                    "kind": "CALL",
                    "summary": "Confirmar propuesta",
                    "due_at": None,
                })
                changed = runtime.reschedule_activity(company_id, activity["id"], {"due_at": "2030-01-02T15:00:00+00:00"})
                self.assertEqual(changed["id"], activity["id"])
                self.assertEqual(changed["contact_id"], activity["contact_id"])
                self.assertEqual(changed["opportunity_id"], activity["opportunity_id"])
                self.assertEqual(changed["kind"], activity["kind"])
                self.assertEqual(changed["summary"], activity["summary"])
                self.assertIsNone(changed["completed_at"])
                self.assertEqual(changed["due_at"], "2030-01-02T15:00:00+00:00")
                events = [row for row in runtime.workspace.registries.timeline.entries() if row.kind == "crm.activity.rescheduled"]
                self.assertEqual(len(events), 1)
                self.assertEqual(events[0].payload["activity_id"], activity["id"])
                self.assertIsNone(events[0].payload["due_at_from"])
                self.assertEqual(events[0].payload["due_at_to"], changed["due_at"])
                same = runtime.reschedule_activity(company_id, activity["id"], {"due_at": changed["due_at"]})
                self.assertEqual(same["updated_at"], changed["updated_at"])
                events = [row for row in runtime.workspace.registries.timeline.entries() if row.kind == "crm.activity.rescheduled"]
                self.assertEqual(len(events), 1)
            finally:
                self._shutdown_runtime(runtime)

    def test_reschedule_rejects_broad_mutation_invalid_date_and_completed_activity(self):
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
                with self.assertRaisesRegex(ValueError, "unsupported activity reschedule fields"):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": "2030-01-02T15:00:00+00:00", "summary": "reescribir"})
                with self.assertRaisesRegex(ValueError, "due_at is required"):
                    runtime.reschedule_activity(company_id, activity["id"], {})
                with self.assertRaisesRegex(ValueError, "valid timestamp"):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": "not-a-date"})
                with self.assertRaisesRegex(ValueError, "valid timestamp"):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": None})
                runtime.complete_activity(company_id, activity["id"])
                with self.assertRaisesRegex(ValueError, "completed activity cannot be rescheduled"):
                    runtime.reschedule_activity(company_id, activity["id"], {"due_at": "2030-01-02T15:00:00+00:00"})
            finally:
                self._shutdown_runtime(runtime)

    def test_due_soon_activity_owner_requires_unique_timestamp_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                due = (datetime.now(timezone.utc) + timedelta(hours=30)).replace(microsecond=0).isoformat()
                activity = runtime.create_activity(company_id, {
                    "contact_id": contact["id"],
                    "opportunity_id": opportunity["id"],
                    "kind": "CALL",
                    "summary": "Llamar",
                    "due_at": due,
                })
                pipeline = runtime.commercial_pipeline(company_id)
                card = next(row for lane in pipeline["lanes"] for row in lane["opportunities"] if row["id"] == opportunity["id"])
                action = {"kind": "pipeline_due_soon", "due_at": due, "action": {"opportunity_id": opportunity["id"]}}
                owner = runtime._pipeline_activity_owner(company_id, action, card)
                self.assertIsNotNone(owner)
                self.assertEqual(owner.id, activity["id"])

                runtime.update_opportunity(company_id, opportunity["id"], {"next_action": "Enviar mensaje", "next_action_at": due})
                ambiguous_card = next(row for lane in runtime.commercial_pipeline(company_id)["lanes"] for row in lane["opportunities"] if row["id"] == opportunity["id"])
                self.assertIsNone(runtime._pipeline_activity_owner(company_id, action, ambiguous_card))
            finally:
                self._shutdown_runtime(runtime)

    def test_action_center_routes_unique_activity_due_soon_without_reprioritizing(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company_id, contact, opportunity = self._fixture(runtime)
                due = (datetime.now(timezone.utc) + timedelta(hours=30)).replace(microsecond=0).isoformat()
                activity = runtime.create_activity(company_id, {
                    "contact_id": contact["id"],
                    "opportunity_id": opportunity["id"],
                    "kind": "TASK",
                    "summary": "Seguimiento futuro",
                    "due_at": due,
                })
                payload = runtime.action_center(company_id)
                rows = [row for row in payload["queue"] if row["kind"] == "pipeline_due_soon" and row["action"].get("opportunity_id") == opportunity["id"]]
                self.assertEqual(len(rows), 1)
                row = rows[0]
                self.assertEqual(row["action"]["view"], "crm")
                self.assertEqual(row["action"]["tab"], "followups")
                self.assertEqual(row["action"]["entity_id"], activity["id"])
                self.assertEqual(row["due_at"], due)
                self.assertEqual(row["owner_resolution"]["activity_id"], activity["id"])
                self.assertTrue(payload["contracts"]["activity_owner_routing_does_not_reprioritize"])
            finally:
                self._shutdown_runtime(runtime)

    def test_http_patch_is_exact_locked_and_rejects_extra_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company_id, contact, opportunity = self._fixture(runtime, name="Activity HTTP")
            activity = runtime.create_activity(company_id, {"contact_id": contact["id"], "opportunity_id": opportunity["id"], "kind": "CALL", "summary": "HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                body = json.dumps({"due_at": "2030-01-02T15:00:00+00:00"}).encode("utf-8")
                request = Request(root + f"/api/companies/{company_id}/activities/{activity['id']}", data=body, headers={"Content-Type": "application/json"}, method="PATCH")
                changed = json.loads(urlopen(request, timeout=5).read().decode("utf-8"))
                self.assertEqual(changed["id"], activity["id"])
                self.assertEqual(changed["due_at"], "2030-01-02T15:00:00+00:00")

                bad = Request(root + f"/api/companies/{company_id}/activities/{activity['id']}", data=json.dumps({"due_at": "2030-01-03T15:00:00+00:00", "summary": "bad"}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="PATCH")
                with self.assertRaises(HTTPError) as raised:
                    urlopen(bad, timeout=5)
                self.assertEqual(raised.exception.code, 400)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_browser_contract_is_explicit_fail_closed_and_non_automatic(self):
        source = (ROOT / "web" / "activity-reschedule-control.js").read_text(encoding="utf-8")
        for required in (
            "POST_W99_ACTIVITY_RESCHEDULE_SCHEMA",
            "crm-activity-reschedule-form",
            "data-post-w99-activity-reschedule-trigger",
            "method:'PATCH'",
            "body:{due_at:dueAt}",
            "crm_unscheduled",
            "pipeline_unscheduled_followup",
            "pipeline_overdue_followup",
            "pipeline_due_soon",
            "Completar o reprogramar seguimiento",
        ):
            self.assertIn(required, source)
        self.assertIn("addEventListener('submit'", source)
        for forbidden in (".click(", "dispatchEvent(", "setInterval(", "sendBeacon(", "method:'POST'"):
            self.assertNotIn(forbidden, source)

    def test_bootstrap_and_docs_preserve_cumulative_chain_and_frozen_main(self):
        docs = (ROOT / "docs" / "POST_W99_EXISTING_ACTIVITY_RESCHEDULE_CONTROL.md").read_text(encoding="utf-8")
        dev = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("`due_at`", docs)
        self.assertIn("actividad completada no se puede reprogramar", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("No constituye W100", docs)
        self.assertIn("Existing Activity Reschedule Control", dev)
        expected = "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control"
        self.assertIn(expected, dev)

        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Bootstrap"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                previous = urlopen(root + "/opportunity-followup-control.js", timeout=5).read().decode("utf-8")
                current = urlopen(root + "/activity-reschedule-control.js", timeout=5).read().decode("utf-8")
                self.assertIn("/activity-reschedule-control.js", previous)
                self.assertIn("POST_W99_ACTIVITY_RESCHEDULE_SCHEMA", current)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)


if __name__ == "__main__":
    unittest.main()
