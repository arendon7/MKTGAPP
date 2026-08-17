import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from binario_marketing.service_wave42_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


def future(minutes=10):
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


class Wave42EditorialRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.runtime.update_company(self.company["id"], {"facebook_page_id": "page-1", "facebook_page_name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def create(self, **changes):
        payload = {"channel": "facebook_page", "kind": "text", "message": "Original"}
        payload.update(changes)
        return self.runtime.create_company_publication(self.company["id"], payload)

    def test_draft_revision_cancels_old_and_creates_new_draft(self):
        old = self.create()
        result = self.runtime.replace_company_publication(self.company["id"], old["id"], {"message": "Corregido", "scheduled_for": None})
        self.assertEqual(result["previous"]["status"], "CANCELLED")
        self.assertEqual(result["replacement"]["status"], "DRAFT")
        self.assertEqual(result["replacement"]["message"], "Corregido")
        self.assertEqual(result["replacement"]["channel"], old["channel"])
        self.assertEqual(result["replacement"]["kind"], old["kind"])
        self.assertEqual(result["replacement"]["target_id"], old["target_id"])

    def test_queued_revision_reprograms_future_and_cancels_old(self):
        old = self.create(scheduled_for=future(15))
        new_time = future(30)
        result = self.runtime.replace_company_publication(self.company["id"], old["id"], {"message": "Nuevo copy", "scheduled_for": new_time})
        replacement = result["replacement"]
        self.assertEqual(result["previous"]["status"], "CANCELLED")
        self.assertEqual(replacement["status"], "QUEUED")
        self.assertEqual(replacement["message"], "Nuevo copy")
        self.assertEqual(datetime.fromisoformat(replacement["scheduled_for"]), datetime.fromisoformat(new_time))

    def test_immutable_identity_fields_are_rejected(self):
        old = self.create()
        for field, value in (("channel", "instagram"), ("kind", "image"), ("target_id", "other"), ("asset_id", "media_x")):
            with self.assertRaisesRegex(ValueError, "unsupported revision fields"):
                self.runtime.replace_company_publication(self.company["id"], old["id"], {field: value})
        self.assertEqual(self.runtime.social.get(old["id"]).status, "DRAFT")

    def test_terminal_or_active_publication_cannot_be_revised(self):
        for status in ("PUBLISHING", "PUBLISHED", "CANCELLED"):
            old = self.create(scheduled_for=future(20))
            if status == "PUBLISHING":
                self.runtime.social.transition(old["id"], "PUBLISHING")
            elif status == "PUBLISHED":
                self.runtime.social.transition(old["id"], "PUBLISHING")
                self.runtime.social.transition(old["id"], "PUBLISHED", remote_id="remote-1")
            else:
                self.runtime.social.transition(old["id"], "CANCELLED")
            with self.assertRaisesRegex(ValueError, "only draft, queued or failed"):
                self.runtime.replace_company_publication(self.company["id"], old["id"], {"message": "No"})

    def test_near_due_queued_requires_explicit_future_time(self):
        old = self.create(scheduled_for=(datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat())
        with self.assertRaisesRegex(ValueError, "too close"):
            self.runtime.replace_company_publication(self.company["id"], old["id"], {"message": "Tarde"})
        with self.assertRaisesRegex(ValueError, "at least 60 seconds"):
            self.runtime.replace_company_publication(self.company["id"], old["id"], {"message": "Tarde", "scheduled_for": (datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat()})
        self.assertEqual(self.runtime.social.get(old["id"]).status, "QUEUED")

    def test_cross_company_revision_fails_closed(self):
        old = self.create()
        other = self.runtime.create_company({"name": "Otra"})
        with self.assertRaises(KeyError):
            self.runtime.replace_company_publication(other["id"], old["id"], {"message": "Intruso"})
        self.assertEqual(self.runtime.social.get(old["id"]).status, "DRAFT")

    def test_race_to_publishing_cancels_replacement(self):
        old = self.create(scheduled_for=future(20))
        original_cancel = self.runtime.cancel_company_publication
        first = True
        def racing_cancel(company_id, publication_id):
            nonlocal first
            if first and publication_id == old["id"]:
                first = False
                self.runtime.social.transition(old["id"], "PUBLISHING")
            return original_cancel(company_id, publication_id)
        self.runtime.cancel_company_publication = racing_cancel
        with self.assertRaisesRegex(ValueError, "changed while"):
            self.runtime.replace_company_publication(self.company["id"], old["id"], {"message": "Revision", "scheduled_for": future(25)})
        rows = self.runtime.social.list(self.company["id"])
        self.assertEqual(sum(1 for row in rows if row.status in {"DRAFT", "QUEUED", "PUBLISHING"}), 1)
        self.assertEqual(self.runtime.social.get(old["id"]).status, "PUBLISHING")
        replacements = [row for row in rows if row.id != old["id"]]
        self.assertEqual(len(replacements), 1)
        self.assertEqual(replacements[0].status, "CANCELLED")


if __name__ == "__main__":
    unittest.main()
