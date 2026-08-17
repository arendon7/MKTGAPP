import json
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.service_wave45_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave45FollowupRescheduleHttpUiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.contact = self.runtime.create_contact(self.company["id"], {"name": "Cliente"})
        self.activity = self.runtime.create_activity(self.company["id"], {
            "contact_id": self.contact["id"],
            "kind": "TASK",
            "summary": "Seguimiento",
            "due_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
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

    def test_followup_reschedule_bundle_is_served(self):
        with urlopen(self.base + "/followup-reschedule.js", timeout=5) as response:
            text = response.read().decode("utf-8")
            status = response.status
        self.assertEqual(status, 200)
        self.assertIn("followupRescheduleSave", text)
        self.assertIn("Reprogramar", text)

    def test_reschedule_endpoint_updates_due_date(self):
        future = datetime.now(timezone.utc) + timedelta(days=3)
        request = Request(
            self.base + f"/api/companies/{self.company['id']}/activities/{self.activity['id']}/reschedule",
            method="POST",
            data=json.dumps({"due_at": future.isoformat()}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(payload["id"], self.activity["id"])
        self.assertGreater(datetime.fromisoformat(payload["due_at"]), datetime.now(timezone.utc))

    def test_loader_orders_wave45_after_wave44(self):
        loader = (ROOT / "web" / "audiences-wave39-loader.js").read_text(encoding="utf-8")
        self.assertIn("actions.src='/daily-actions.js'", loader)
        self.assertIn("reschedule.src='/followup-reschedule.js'", loader)
        self.assertIn("actions.addEventListener('load',loadFollowupReschedule", loader)
        self.assertIn("#daily-actions-wave44-style", loader)


if __name__ == "__main__":
    unittest.main()
