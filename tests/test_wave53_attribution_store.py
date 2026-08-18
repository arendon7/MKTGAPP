import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from binario_marketing.attribution_store import AttributionStore, build_tracked_url


COMPANY_A = "company_0123456789abcdef01234567"
COMPANY_B = "company_89abcdef0123456701234567"
CAMPAIGN = "campaign_0123456789abcdef01234567"
MEDIA = "media_0123456789abcdef01234567"
CONTACT = "contact_0123456789abcdef01234567"
OPPORTUNITY = "opportunity_0123456789abcdef01234567"


class Wave53AttributionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = AttributionStore(Path(self.tmp.name) / "attribution")

    def tearDown(self):
        self.tmp.cleanup()

    def _link(self, **overrides):
        payload = {
            "campaign_id": CAMPAIGN,
            "creative_media_id": MEDIA,
            "destination_url": "https://example.com/landing?existing=1&utm_source=old&bm_tid=bm_deadbeefdeadbeefdeadbeef#form",
            "utm_source": "instagram",
            "utm_medium": "paid_social",
            "utm_campaign": "captacion_q3",
            "utm_id": CAMPAIGN,
            "utm_content": MEDIA,
            "utm_source_platform": "instagram",
        }
        payload.update(overrides)
        return self.store.create_link(COMPANY_A, payload)

    def test_tracked_url_preserves_business_query_and_replaces_managed_tracking(self):
        row = self._link()
        parsed = urlsplit(row.tracked_url)
        query = parse_qs(parsed.query)
        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.fragment, "form")
        self.assertEqual(query["existing"], ["1"])
        self.assertEqual(query["utm_source"], ["instagram"])
        self.assertEqual(query["utm_medium"], ["paid_social"])
        self.assertEqual(query["utm_campaign"], ["captacion_q3"])
        self.assertEqual(query["utm_id"], [CAMPAIGN])
        self.assertEqual(query["utm_content"], [MEDIA])
        self.assertEqual(query["bm_tid"], [row.tracking_code])
        self.assertNotEqual(query["bm_tid"], ["bm_deadbeefdeadbeefdeadbeef"])
        self.assertRegex(row.tracking_code, r"^bm_[0-9a-f]{24}$")

    def test_url_builder_rejects_insecure_embedded_credentials_and_secret_query(self):
        kwargs = dict(
            tracking_code="bm_0123456789abcdef01234567",
            utm_source="instagram",
            utm_medium="paid_social",
            utm_campaign="campaign",
            utm_id="campaign_0123456789abcdef01234567",
        )
        for url in (
            "http://example.com/landing",
            "https://user:password@example.com/landing",
            "https://example.com/landing?access_token=secret",
            "https://example.com/landing?token=secret",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                build_tracked_url(url, **kwargs)

    def test_claim_requires_exact_code_and_is_idempotent_for_same_evidence(self):
        link = self._link()
        payload = {
            "tracking_code": link.tracking_code,
            "contact_id": CONTACT,
            "opportunity_id": OPPORTUNITY,
            "evidence": "CAPTURED_TRACKING_CODE",
            "captured_at": "2026-08-18T01:02:03+00:00",
        }
        first = self.store.create_claim(COMPANY_A, payload)
        second = self.store.create_claim(COMPANY_A, payload)
        self.assertEqual(first.id, second.id)
        self.assertEqual(first.tracking_link_id, link.id)
        self.assertEqual(len(self.store.list_claims(COMPANY_A)), 1)
        with self.assertRaises(KeyError):
            self.store.create_claim(COMPANY_A, {**payload, "tracking_code": "bm_ffffffffffffffffffffffff"})

    def test_company_boundaries_and_claim_shape_fail_closed(self):
        link = self._link()
        with self.assertRaises(KeyError):
            self.store.get_link(COMPANY_B, link.id)
        with self.assertRaises(KeyError):
            self.store.get_link_by_code(COMPANY_B, link.tracking_code)
        with self.assertRaisesRegex(ValueError, "contact_id or opportunity_id"):
            self.store.create_claim(COMPANY_A, {"tracking_code": link.tracking_code})
        with self.assertRaisesRegex(ValueError, "unsupported attribution evidence"):
            self.store.create_claim(COMPANY_A, {
                "tracking_code": link.tracking_code,
                "contact_id": CONTACT,
                "evidence": "DATE_CORRELATION",
            })


if __name__ == "__main__":
    unittest.main()
