import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.service_wave43_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave43DailyOperationsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.update_company(self.company["id"], {"facebook_page_id": "page-1"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_dashboard_exposes_publication_and_crm_priority_inputs(self):
        overdue_when = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        queued = self.runtime.create_company_publication(self.company["id"], {
            "channel": "facebook_page",
            "kind": "text",
            "message": "Programación vencida",
            "scheduled_for": overdue_when,
        })
        failed = self.runtime.create_company_publication(self.company["id"], {
            "channel": "facebook_page",
            "kind": "text",
            "message": "Publicación fallida",
            "scheduled_for": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        })
        self.runtime.social.transition(failed["id"], "PUBLISHING")
        self.runtime.social.transition(failed["id"], "FAILED", error="Provider test failure")
        contact = self.runtime.create_contact(self.company["id"], {"name": "Cliente"})
        self.runtime.create_activity(self.company["id"], {
            "contact_id": contact["id"],
            "kind": "TASK",
            "summary": "Llamar al cliente",
            "due_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        })

        dashboard = self.runtime.ops_dashboard(self.company["id"])
        self.assertGreaterEqual(dashboard["summary"]["failed"], 1)
        self.assertGreaterEqual(dashboard["overdue"], 1)
        self.assertGreaterEqual(dashboard["crm"]["overdue_activities"], 1)
        self.assertTrue(any(row["id"] == queued["id"] for row in self.runtime.ops_calendar(self.company["id"])))
        self.assertEqual(dashboard["crm"]["next_activities"][0]["summary"], "Llamar al cliente")

    def test_daily_bundle_is_local_read_only_and_prioritized(self):
        ui = (ROOT / "web" / "daily-ops.js").read_text(encoding="utf-8")
        for required in (
            "HOY · PRIORIDADES",
            "Qué necesita tu atención",
            "REQUIEREN ATENCIÓN",
            "Publicación",
            "CRM vencido",
            "Publicación hoy",
            "CRM hoy",
            "Abrir CRM",
            "Bandeja",
        ):
            self.assertIn(required, ui)
        self.assertIn("priority:0", ui)
        self.assertIn("priority:1", ui)
        self.assertIn("overdue?2:4", ui)
        self.assertIn("priority:3", ui)
        self.assertIn("items.sort((a,b)=>a.priority-b.priority", ui)
        for forbidden in (
            "/api/meta/",
            "fetch('https://",
            'fetch("https://',
            "method:'POST'",
            "method:'DELETE'",
            "method:'PATCH'",
            "setInterval(",
            "MutationObserver(",
        ):
            self.assertNotIn(forbidden, ui)


if __name__ == "__main__":
    unittest.main()
