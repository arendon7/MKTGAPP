import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.capture_store import FirstPartyCaptureStore


class Wave54CaptureStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = FirstPartyCaptureStore(Path(self.tmp.name))
        self.company = "company_0123456789abcdef01234567"
        self.payload = {
            "tracking_link_id": "tracking_0123456789abcdef01234567",
            "tracking_code": "bm_0123456789abcdef01234567",
            "contact_id": "contact_0123456789abcdef01234567",
            "opportunity_id": None,
            "source": "CRM_CONTACT_CREATE",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
            "utm_campaign": "campana_w54",
            "utm_id": "campaign_0123456789abcdef01234567",
            "utm_content": "creative_a",
            "utm_term": None,
            "utm_source_platform": "instagram",
            "landing_url": "https://example.com/form?email=private@example.com&foo=bar#section",
            "referrer_url": "https://ref.example/path?token=not-persisted",
            "bridge_version": "1.0.0",
            "client_captured_at": "2026-08-18T01:00:00-05:00",
            "received_at": "2026-08-18T06:00:03+00:00",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_capture_is_durable_idempotent_and_pii_minimized(self):
        row = self.store.create(self.company, self.payload)
        again = self.store.create(self.company, self.payload)
        self.assertEqual(row.id, again.id)
        self.assertEqual(row.utm_validation, "MATCHED_CANONICAL_LINK")
        self.assertEqual(row.landing_host, "example.com")
        self.assertEqual(row.referrer_host, "ref.example")
        self.assertEqual(row.received_at, "2026-08-18T06:00:03+00:00")
        self.assertEqual(row.client_captured_at, "2026-08-18T06:00:00+00:00")
        text = json.dumps(row.__dict__)
        self.assertNotIn("private@example.com", text)
        self.assertNotIn("foo=bar", text)
        self.assertNotIn("not-persisted", text)
        loaded = self.store.get(self.company, row.id)
        self.assertEqual(loaded, row)
        self.assertEqual(len(self.store.list(self.company)), 1)

    def test_capture_requires_crm_reference_and_rejects_secret_fields(self):
        payload = dict(self.payload)
        payload["contact_id"] = None
        with self.assertRaisesRegex(ValueError, "contact_id or opportunity_id"):
            self.store.create(self.company, payload)
        payload = dict(self.payload)
        payload["access_token"] = "secret"
        with self.assertRaisesRegex(ValueError, "credentials must not be persisted"):
            self.store.create(self.company, payload)

    def test_cross_company_get_fails_closed(self):
        row = self.store.create(self.company, self.payload)
        with self.assertRaises(KeyError):
            self.store.get("company_aaaaaaaaaaaaaaaaaaaaaaaa", row.id)

    def test_invalid_urls_and_client_time_fail_closed(self):
        payload = dict(self.payload)
        payload["landing_url"] = "javascript:alert(1)"
        with self.assertRaisesRegex(ValueError, "landing_url"):
            self.store.create(self.company, payload)
        payload = dict(self.payload)
        payload["client_captured_at"] = "2026-08-18T01:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.store.create(self.company, payload)


if __name__ == "__main__":
    unittest.main()
