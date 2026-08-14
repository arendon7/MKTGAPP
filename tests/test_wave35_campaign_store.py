import tempfile
import unittest
from pathlib import Path

from binario_marketing.campaign_store import CampaignStore


COMPANY_A = "company_" + "a" * 24
COMPANY_B = "company_" + "b" * 24
CONTACT = "contact_" + "c" * 24
MEDIA = "media_" + "d" * 24
PUBLICATION = "e" * 32


class CampaignStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = CampaignStore(Path(self.tmp.name) / "campaigns")

    def tearDown(self):
        self.tmp.cleanup()

    def test_create_deduplicates_refs_and_persists_planning_state(self):
        row = self.store.create(COMPANY_A, {
            "name": "Lanzamiento Wondergreen",
            "objective": "LEADS",
            "channels": ["instagram", "email", "instagram"],
            "audience_contact_ids": [CONTACT, CONTACT],
            "media_ids": [MEDIA],
            "publication_ids": [PUBLICATION],
            "start_at": "2030-01-02T08:00:00+00:00",
            "end_at": "2030-01-20T18:00:00+00:00",
        })
        self.assertEqual(row.status, "PLANNING")
        self.assertEqual(row.channels, ("instagram", "email"))
        self.assertEqual(row.audience_contact_ids, (CONTACT,))
        self.assertEqual(row.media_ids, (MEDIA,))
        self.assertEqual(row.publication_ids, (PUBLICATION,))
        loaded = self.store.get_for_company(COMPANY_A, row.id)
        self.assertEqual(loaded, row)

    def test_company_boundary_and_status_summary(self):
        first = self.store.create(COMPANY_A, {"name": "A"})
        second = self.store.create(COMPANY_A, {"name": "B", "status": "READY"})
        self.store.create(COMPANY_B, {"name": "Other", "status": "IN_PROGRESS"})
        with self.assertRaises(KeyError):
            self.store.get_for_company(COMPANY_B, first.id)
        summary = self.store.summary(COMPANY_A)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["planning"], 1)
        self.assertEqual(summary["ready"], 1)
        self.assertEqual(summary["in_progress"], 0)
        updated = self.store.update(COMPANY_A, second.id, {"status": "COMPLETED"})
        self.assertEqual(updated.status, "COMPLETED")

    def test_invalid_date_order_channel_and_reference_shape_are_rejected(self):
        with self.assertRaises(ValueError):
            self.store.create(COMPANY_A, {
                "name": "Bad dates",
                "start_at": "2030-02-01T00:00:00+00:00",
                "end_at": "2030-01-01T00:00:00+00:00",
            })
        with self.assertRaises(ValueError):
            self.store.create(COMPANY_A, {"name": "Bad channel", "channels": ["sms"]})
        with self.assertRaises(ValueError):
            self.store.create(COMPANY_A, {"name": "Bad refs", "media_ids": ["../../etc/passwd"]})
        with self.assertRaises(ValueError):
            self.store.create(COMPANY_A, {"name": "Bad status", "status": "PUBLISHED"})


if __name__ == "__main__":
    unittest.main()
