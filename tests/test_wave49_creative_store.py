import tempfile
import unittest
from pathlib import Path

from binario_marketing.creative_store import CreativeStore


class Wave49CreativeStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = CreativeStore(Path(self.tmp.name))
        self.company = "company_" + "a" * 24
        self.media = "media_" + "b" * 24

    def tearDown(self):
        self.tmp.cleanup()

    def test_upsert_roundtrip_and_links(self):
        row = self.store.upsert(self.company, self.media, {
            "title": "Reel lanzamiento",
            "stage": "READY",
            "purpose": "LEADS",
            "campaign_id": "campaign_" + "c" * 24,
            "channels": ["instagram", "paid_media", "instagram"],
            "primary_copy": "Prueba el producto",
            "headline": "Nuevo",
            "call_to_action": "LEARN_MORE",
            "destination_url": "https://example.com/landing",
            "public_media_url": "https://cdn.example.com/reel.mp4",
            "publish_at": "2026-08-20T15:00:00-05:00",
            "notes": "Hipótesis A",
        })
        self.assertEqual(row.channels, ("instagram", "paid_media"))
        self.assertEqual(row.publish_at, "2026-08-20T20:00:00+00:00")
        publication = "1" * 32
        paid = "2" * 32
        row = self.store.link_publication(self.company, self.media, publication, stage="SCHEDULED")
        row = self.store.link_paid_media(self.company, self.media, paid)
        self.assertEqual(row.stage, "PAID")
        self.assertEqual(row.publication_ids, (publication,))
        self.assertEqual(row.paid_media_ids, (paid,))
        loaded = self.store.get(self.company, self.media)
        self.assertEqual(loaded, row)

    def test_rejects_cross_contract_values(self):
        with self.assertRaisesRegex(ValueError, "campaign"):
            self.store.upsert(self.company, self.media, {"title": "x", "campaign_id": "bad"})
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self.store.upsert(self.company, self.media, {"title": "x", "destination_url": "http://example.com"})
        with self.assertRaisesRegex(ValueError, "channel"):
            self.store.upsert(self.company, self.media, {"title": "x", "channels": ["tiktok"]})


if __name__ == "__main__":
    unittest.main()
