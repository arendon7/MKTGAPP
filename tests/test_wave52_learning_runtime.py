import io
import tempfile
import unittest
from pathlib import Path

from binario_marketing.service_wave52_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave52LearningRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        raw = b"\x89PNG\r\n\x1a\nwave52"
        self.media = self.runtime.upload_company_media(
            self.company["id"], "creative.png", "image", io.BytesIO(raw), len(raw)
        )
        self.campaign = self.runtime.create_campaign(self.company["id"], {
            "name": "Captación Q3",
            "objective": "LEADS",
            "status": "IN_PROGRESS",
            "channels": ["instagram"],
            "media_ids": [self.media["id"]],
        })
        self.runtime.upsert_company_creative(self.company["id"], self.media["id"], {
            "title": "Creative A",
            "stage": "READY",
            "purpose": "LEADS",
            "campaign_id": self.campaign["id"],
            "channels": ["instagram", "paid_media"],
            "primary_copy": "Mensaje A",
        })
        self.publication_id = "a" * 32
        self.draft_id = "b" * 32
        self.runtime.creatives.link_publication(
            self.company["id"], self.media["id"], self.publication_id, stage="PUBLISHED"
        )
        self.runtime.creatives.link_paid_media(
            self.company["id"], self.media["id"], self.draft_id
        )
        self.runtime.create_opportunity(self.company["id"], {
            "title": "Venta atribuida solo a empresa",
            "stage": "WON",
            "value": 500000,
            "currency": "COP",
        })
        self.remote_calls = []
        self.runtime.social_analytics_meta = self._social_readback
        self.runtime.company_paid_media = self._paid_rows
        self.runtime.company_paid_media_observability = self._paid_readback

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _social_readback(self, company_id, *, limit=12):
        self.remote_calls.append(("social", company_id, limit))
        return {
            "configured": True,
            "coverage": {"eligible": 1, "requested": 1, "observed": 1, "measured": 1, "errors": 0},
            "totals": {"reach": 1000, "views": 1200, "total_interactions": 80},
            "observations": [{
                "id": self.publication_id,
                "channel": "instagram",
                "kind": "image",
                "remote_state": "PUBLISHED",
                "available": True,
                "metrics": {"reach": 1000, "views": 1200, "likes": 60, "comments": 10, "shares": 5, "saved": 5, "total_interactions": 80},
                "provider_error": None,
            }],
        }

    def _paid_rows(self, company_id):
        return [{
            "id": self.draft_id,
            "status": "REMOTE_PAUSED",
            "campaign_id": "remote_campaign_1",
            "ad_id": "remote_ad_1",
            "marketing_campaign": {"id": self.campaign["id"], "name": self.campaign["name"]},
            "creative_source": {"id": self.media["id"]},
            "plan": {"currency": "COP"},
        }]

    def _paid_readback(self, company_id, draft_id, date_preset=None):
        self.remote_calls.append(("paid", company_id, draft_id, date_preset))
        return {
            "insights": {"impressions": 2000, "reach": 1500, "clicks": 100, "spend": 250000, "ctr": 99},
            "safety": {"configured_paused": True, "explicit_active_detected": False},
        }

    def test_explicit_refresh_persists_sanitized_evidence_and_rollups(self):
        result = self.runtime.refresh_learning(self.company["id"], {
            "date_preset": "last_7d", "social_limit": 20, "paid_limit": 20,
        })
        self.assertTrue(result["safety"]["provider_refresh_performed"])
        self.assertFalse(result["safety"]["provider_mutation_performed"])
        self.assertEqual(len(self.remote_calls), 2)
        snapshot = result["latest_snapshot"]
        self.assertEqual(snapshot["social"]["totals"]["reach"], 1000)
        self.assertEqual(snapshot["paid_media"]["totals"]["clicks"], 100)
        self.assertFalse(snapshot["crm"]["attributed_to_campaign"])
        self.assertEqual(snapshot["crm"]["value_by_currency"]["COP"]["won_value"], 500000)

        creative = next(row for row in result["creatives"] if row["media_id"] == self.media["id"])
        self.assertEqual(creative["metrics"]["organic_reach"], 1000)
        self.assertEqual(creative["metrics"]["impressions"], 2000)
        self.assertEqual(creative["metrics"]["paid_ctr"], 5.0)
        self.assertEqual(creative["metrics"]["organic_interaction_rate"], 8.0)
        campaign = next(row for row in result["campaigns"] if row["id"] == self.campaign["id"])
        self.assertEqual(campaign["metrics"]["clicks"], 100)
        self.assertFalse(result["attribution"]["crm_to_campaign"])

    def test_get_payload_never_refreshes_provider_and_decision_never_executes(self):
        self.runtime.refresh_learning(self.company["id"], {})
        self.remote_calls.clear()
        before_paid = self._paid_rows(self.company["id"])
        payload = self.runtime.learning_payload(self.company["id"])
        self.assertEqual(self.remote_calls, [])
        self.assertFalse(payload["safety"]["provider_refresh_performed"])

        decision = self.runtime.record_learning_decision(self.company["id"], {
            "entity_kind": "CREATIVE",
            "entity_id": self.media["id"],
            "action": "ITERATE",
            "rationale": "Mantener inversión y probar otro ángulo.",
            "snapshot_id": payload["latest_snapshot"]["id"],
        })
        self.assertEqual(decision["action"], "ITERATE")
        self.assertEqual(self.remote_calls, [])
        self.assertEqual(self._paid_rows(self.company["id"]), before_paid)
        after = self.runtime.learning_payload(self.company["id"])
        creative = next(row for row in after["creatives"] if row["media_id"] == self.media["id"])
        self.assertEqual(creative["latest_decision"]["action"], "ITERATE")

    def test_ai_context_receives_observed_metrics_with_attribution_caveat(self):
        self.runtime.refresh_learning(self.company["id"], {})
        self.remote_calls.clear()
        context = self.runtime._ai_context(
            self.company["id"], task="STRATEGY", campaign_id=None, creative_media_id=None
        )
        self.assertEqual(self.remote_calls, [])
        self.assertIn("learning", context)
        self.assertFalse(context["learning"]["attribution"]["crm_to_campaign"])
        creative = next(row for row in context["learning"]["creatives"] if row["media_id"] == self.media["id"])
        self.assertEqual(creative["metrics"]["paid_ctr"], 5.0)
        self.assertEqual(context["learning"]["crm_company_outcome"]["value_by_currency"]["COP"]["won_count"], 1)


if __name__ == "__main__":
    unittest.main()
