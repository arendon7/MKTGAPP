import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.service_wave44_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave44DailyActionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_existing_crm_completion_contract_removes_daily_priority(self):
        contact = self.runtime.create_contact(self.company["id"], {"name": "Cliente"})
        activity = self.runtime.create_activity(self.company["id"], {
            "contact_id": contact["id"],
            "kind": "TASK",
            "summary": "Llamar al cliente",
            "due_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        })
        before = self.runtime.ops_dashboard(self.company["id"])["crm"]
        self.assertEqual(before["overdue_activities"], 1)
        self.assertTrue(any(row["id"] == activity["id"] for row in before["next_activities"]))

        completed = self.runtime.complete_activity(self.company["id"], activity["id"])
        self.assertTrue(completed["completed_at"])
        after = self.runtime.ops_dashboard(self.company["id"])["crm"]
        self.assertEqual(after["overdue_activities"], 0)
        self.assertFalse(any(row["id"] == activity["id"] for row in after["next_activities"]))

    def test_daily_action_bundle_only_completes_local_crm_and_deep_links_editorial(self):
        ui = (ROOT / "web" / "daily-actions.js").read_text(encoding="utf-8")
        for required in (
            "Completar",
            "Gestionar",
            "dailyActionCompleteActivity",
            "editorialState.selectedId=row.id",
            "crmState.tab='followups'",
            "/activities/",
            "/complete",
            "window.confirm",
            "Ninguna acción publica, reintenta ni responde automáticamente",
        ):
            self.assertIn(required, ui)
        self.assertEqual(ui.count("method:'POST'"), 1)
        for forbidden in (
            "/api/meta/",
            "fetch('https://",
            'fetch("https://',
            "setInterval(",
            "MutationObserver(",
            "publish-now",
        ):
            self.assertNotIn(forbidden, ui)


if __name__ == "__main__":
    unittest.main()
