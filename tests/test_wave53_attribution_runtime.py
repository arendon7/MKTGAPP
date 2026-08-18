import io
import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.service_wave53_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]


class Wave53AttributionRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.other_company = self.runtime.create_company({"name": "Otra Empresa"})
        self.contact = self.runtime.create_contact(self.company["id"], {
            "name": "Persona Privada",
            "email": "private@example.com",
            "phone": "+57 300 000 0000",
        })
        self.opportunity = self.runtime.create_opportunity(self.company["id"], {
            "contact_id": self.contact["id"],
            "title": "Venta atribuible",
            "stage": "WON",
            "value": 2500000,
            "currency": "COP",
        })
        self.campaign_a = self.runtime.create_campaign(self.company["id"], {
            "name": "Captación Instagram",
            "objective": "LEADS",
            "status": "IN_PROGRESS",
            "channels": ["instagram"],
        })
        self.campaign_b = self.runtime.create_campaign(self.company["id"], {
            "name": "Retargeting Meta",
            "objective": "SALES",
            "status": "IN_PROGRESS",
            "channels": ["instagram"],
        })
        raw = b"\x89PNG\r\n\x1a\nwave53"
        self.media = self.runtime.upload_company_media(
            self.company["id"], "creative.png", "image", io.BytesIO(raw), len(raw)
        )
        self.runtime.upsert_company_creative(self.company["id"], self.media["id"], {
            "title": "Creativo Captación",
            "stage": "READY",
            "purpose": "LEADS",
            "campaign_id": self.campaign_a["id"],
            "channels": ["instagram", "paid_media"],
            "primary_copy": "Copy de captación",
            "destination_url": "https://example.com/landing?product=2grow",
        })

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _link(self, campaign, *, creative_media_id=None, source="instagram"):
        return self.runtime.create_tracking_link(self.company["id"], {
            "campaign_id": campaign["id"],
            "creative_media_id": creative_media_id,
            "destination_url": "https://example.com/landing?product=2grow",
            "utm_source": source,
            "utm_medium": "paid_social",
        })

    def test_tracking_link_uses_campaign_and_creative_truth_without_provider_calls(self):
        self.runtime.social_analytics_meta = lambda *a, **k: (_ for _ in ()).throw(AssertionError("provider read called"))
        self.runtime.company_paid_media_observability = lambda *a, **k: (_ for _ in ()).throw(AssertionError("provider read called"))
        result = self._link(self.campaign_a, creative_media_id=self.media["id"])
        self.assertEqual(result["campaign_id"], self.campaign_a["id"])
        self.assertEqual(result["creative_media_id"], self.media["id"])
        self.assertEqual(result["utm_source"], "instagram")
        self.assertEqual(result["utm_medium"], "paid_social")
        self.assertEqual(result["utm_id"], self.campaign_a["id"])
        self.assertEqual(result["utm_content"], self.media["id"])
        self.assertIn("bm_tid=bm_", result["tracked_url"])
        self.assertIn("utm_campaign=captacion_instagram", result["tracked_url"])
        self.assertEqual(self.runtime.attribution_payload(self.company["id"])["summary"]["captured_touches"], 0)

    def test_creative_cannot_be_attributed_to_a_different_campaign(self):
        with self.assertRaisesRegex(ValueError, "creative must be linked"):
            self._link(self.campaign_b, creative_media_id=self.media["id"])
        other_campaign = self.runtime.create_campaign(self.other_company["id"], {
            "name": "Campaña ajena", "objective": "LEADS"
        })
        with self.assertRaises(KeyError):
            self.runtime.create_tracking_link(self.company["id"], {
                "campaign_id": other_campaign["id"],
                "destination_url": "https://example.com/landing",
                "utm_source": "instagram",
                "utm_medium": "social",
            })

    def test_last_captured_touch_credits_one_opportunity_once(self):
        early = self._link(self.campaign_a, source="instagram")
        late = self._link(self.campaign_b, source="facebook")
        self.runtime.record_attribution_claim(self.company["id"], {
            "tracking_code": early["tracking_code"],
            "opportunity_id": self.opportunity["id"],
            "captured_at": "2026-08-17T10:00:00+00:00",
        })
        self.runtime.record_attribution_claim(self.company["id"], {
            "tracking_code": late["tracking_code"],
            "opportunity_id": self.opportunity["id"],
            "captured_at": "2026-08-17T11:00:00+00:00",
        })
        result = self.runtime.attribution_payload(self.company["id"])
        by_id = {row["id"]: row for row in result["campaigns"]}
        self.assertEqual(result["summary"]["captured_touches"], 2)
        self.assertEqual(result["summary"]["attributed_opportunities"], 1)
        self.assertEqual(result["summary"]["attributed_won"], 1)
        self.assertEqual(result["summary"]["value_by_currency"]["COP"]["won_value"], 2500000)
        self.assertEqual(by_id[self.campaign_a["id"]]["touches"], 1)
        self.assertEqual(by_id[self.campaign_a["id"]]["attributed_opportunities"], 0)
        self.assertEqual(by_id[self.campaign_b["id"]]["touches"], 1)
        self.assertEqual(by_id[self.campaign_b["id"]]["attributed_opportunities"], 1)
        self.assertEqual(by_id[self.campaign_b["id"]]["value_by_currency"]["COP"]["won_value"], 2500000)
        self.assertEqual(sum(row["attributed_opportunities"] for row in result["campaigns"]), 1)

    def test_local_payload_never_queries_provider_and_partial_attribution_flows_into_learning(self):
        link = self._link(self.campaign_a)
        self.runtime.record_attribution_claim(self.company["id"], {
            "tracking_code": link["tracking_code"],
            "opportunity_id": self.opportunity["id"],
        })
        self.runtime.social_analytics_meta = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Meta called"))
        self.runtime.company_paid_media_observability = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Ads called"))
        result = self.runtime.attribution_payload(self.company["id"])
        learning = self.runtime.learning_payload(self.company["id"])
        self.assertFalse(result["model"]["clicks_observed"])
        self.assertFalse(result["model"]["temporal_inference"])
        self.assertEqual(result["model"]["opportunity_credit"], "LAST_CAPTURED_TOUCH")
        self.assertTrue(learning["attribution"]["crm_to_campaign_deterministic_partial"])
        self.assertEqual(learning["attribution"]["crm_to_campaign_coverage_percent"], 100.0)
        self.assertFalse(learning["safety"]["provider_refresh_performed"])

    def test_ai_context_contains_aggregate_attribution_but_no_contact_pii_or_tracking_urls(self):
        link = self._link(self.campaign_a)
        self.runtime.record_attribution_claim(self.company["id"], {
            "tracking_code": link["tracking_code"],
            "opportunity_id": self.opportunity["id"],
        })
        context = self.runtime._ai_context(
            self.company["id"], task="STRATEGY", campaign_id=None, creative_media_id=None
        )
        text = json.dumps(context, ensure_ascii=False)
        self.assertEqual(context["attribution"]["summary"]["attributed_opportunities"], 1)
        self.assertEqual(context["attribution"]["model"]["opportunity_credit"], "LAST_CAPTURED_TOUCH")
        self.assertNotIn("Persona Privada", text)
        self.assertNotIn("private@example.com", text)
        self.assertNotIn("300 000 0000", text)
        self.assertNotIn(self.contact["id"], text)
        self.assertNotIn(link["tracking_code"], text)
        self.assertNotIn(link["tracked_url"], text)


if __name__ == "__main__":
    unittest.main()
