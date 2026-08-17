import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.service_wave45_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave45FollowupRescheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.contact = self.runtime.create_contact(self.company["id"], {"name": "Cliente"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def create_overdue(self):
        return self.runtime.create_activity(self.company["id"], {
            "contact_id": self.contact["id"],
            "kind": "TASK",
            "summary": "Seguimiento comercial",
            "due_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
        })

    def test_reschedule_moves_overdue_activity_to_future(self):
        activity = self.create_overdue()
        self.assertEqual(self.runtime.ops_dashboard(self.company["id"])["crm"]["overdue_activities"], 1)
        future = datetime.now(timezone.utc) + timedelta(days=2)
        row = self.runtime.reschedule_activity(self.company["id"], activity["id"], {"due_at": future.isoformat()})
        self.assertEqual(row["id"], activity["id"])
        self.assertIsNone(row["completed_at"])
        self.assertGreater(datetime.fromisoformat(row["due_at"]), datetime.now(timezone.utc))
        self.assertEqual(self.runtime.ops_dashboard(self.company["id"])["crm"]["overdue_activities"], 0)

    def test_reschedule_rejects_past_and_unknown_fields(self):
        activity = self.create_overdue()
        with self.assertRaisesRegex(ValueError, "future"):
            self.runtime.reschedule_activity(self.company["id"], activity["id"], {"due_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()})
        with self.assertRaisesRegex(ValueError, "unsupported reschedule fields"):
            self.runtime.reschedule_activity(self.company["id"], activity["id"], {"due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(), "summary": "mutate"})

    def test_completed_activity_cannot_be_rescheduled(self):
        activity = self.create_overdue()
        self.runtime.complete_activity(self.company["id"], activity["id"])
        with self.assertRaisesRegex(ValueError, "completed activity"):
            self.runtime.reschedule_activity(self.company["id"], activity["id"], {"due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})

    def test_wave45_ui_has_one_explicit_local_mutation(self):
        ui = (ROOT / "web" / "followup-reschedule.js").read_text(encoding="utf-8")
        for required in ("Reprogramar", "Guardar fecha", "/reschedule", "due_at", "La nueva fecha debe quedar en el futuro", "No envía mensajes, correos ni respuestas"):
            self.assertIn(required, ui)
        self.assertEqual(ui.count("method:'POST'"), 1)
        for forbidden in ("/api/meta/", "fetch('https://", 'fetch("https://', "setInterval(", "MutationObserver(", "publish-now", "send-message", "reply"):
            self.assertNotIn(forbidden, ui)


if __name__ == "__main__":
    unittest.main()
