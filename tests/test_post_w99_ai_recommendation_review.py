from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.ai_recommendation_review import (
    RecommendationReviewConflict,
    RecommendationReviewStore,
    current_recommendations,
    extend_action_center,
    project_recommendation_review,
)
from binario_marketing.service_post_w99_ai_recommendation_review_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def _session(session_id: str, *, created_at: str, campaign_id: str = "campaign_" + "a" * 24, title: str = "Mejorar CTA", priority: str = "HIGH") -> dict:
    return {
        "id": session_id,
        "task": "CAMPAIGN",
        "campaign_id": campaign_id,
        "creative_media_id": None,
        "created_at": created_at,
        "context": {"selected_campaign": {"name": "Campaña exacta"}},
        "output": {
            "recommendations": [
                {"title": title, "why": "La evidencia sugiere revisar el mensaje.", "priority": priority, "area": "CAMPAIGN", "next_step": "Preparar una variante y revisarla manualmente."},
                {"title": "Revisar oferta", "why": "La propuesta puede ser más concreta.", "priority": "LOW", "area": "CONTENT", "next_step": "Comparar la oferta actual con una alternativa."},
            ]
        },
    }


def _base_action_center(campaign_id: str) -> dict:
    optional = {
        "id": f"campaign:optional-ai:{campaign_id}", "rank": 88, "urgency": "LOW", "source": "CAMPAIGN", "kind": "optional_ai",
        "title": "Análisis IA opcional", "detail": "Puede analizarse", "action": {"label": "Analizar", "view": "intelligence", "tab": None, "entity_id": None, "lead_id": None, "contact_id": None, "opportunity_id": None, "campaign_id": campaign_id, "media_id": None},
        "reason": {"code": "CAMPAIGN_OPTIONAL_AI", "explanation": "IA opcional"}, "due_at": None, "blocking": False,
        "requires_human_action": True, "read_only_recommendation": True,
    }
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": "company_" + "b" * 24, "name": "Empresa"},
        "queue": [optional], "next_action": optional,
        "focus": {"now": [], "next": [], "later": [optional]},
        "summary": {"queue_total": 1, "blocking": 0, "critical": 0, "high": 0, "medium": 0, "low": 1, "by_source": {"CAMPAIGN": 1}},
        "contracts": {}, "safety": {},
    }


class AIRecommendationReviewPureTests(unittest.TestCase):
    def test_only_latest_session_per_exact_target_can_create_pending_review(self):
        old = _session("ai_" + "1" * 24, created_at="2026-09-07T10:00:00+00:00", title="Vieja")
        new = _session("ai_" + "2" * 24, created_at="2026-09-07T11:00:00+00:00", title="Nueva")
        rows = current_recommendations([new, old])
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["session_id"] for row in rows}, {new["id"]})
        self.assertEqual(rows[0]["title"], "Nueva")
        self.assertRegex(rows[0]["recommendation_id"], r"^airec_[0-9a-f]{24}$")
        self.assertRegex(rows[0]["recommendation_sha256"], r"^[0-9a-f]{64}$")

    def test_store_is_idempotent_for_same_decision_and_conflicts_on_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = RecommendationReviewStore(Path(tmp))
            rec = current_recommendations([_session("ai_" + "3" * 24, created_at="2026-09-07T11:00:00+00:00")])[0]
            first = store.record("company_" + "c" * 24, recommendation=rec["recommendation_id"], session_id=rec["session_id"], digest=rec["recommendation_sha256"], decision="ACCEPTED")
            second = store.record("company_" + "c" * 24, recommendation=rec["recommendation_id"], session_id=rec["session_id"], digest=rec["recommendation_sha256"], decision="ACCEPTED")
            self.assertEqual(first, second)
            with self.assertRaises(RecommendationReviewConflict):
                store.record("company_" + "c" * 24, recommendation=rec["recommendation_id"], session_id=rec["session_id"], digest=rec["recommendation_sha256"], decision="DISMISSED")

    def test_projection_groups_one_session_and_ai_priority_is_context_only(self):
        session = _session("ai_" + "4" * 24, created_at="2026-09-07T11:00:00+00:00", priority="HIGH")
        projection = project_recommendation_review("company_" + "d" * 24, sessions=[session], reviews=[])
        self.assertEqual(projection["summary"]["current_sessions_with_pending_review"], 1)
        self.assertEqual(projection["summary"]["pending_recommendations"], 2)
        self.assertEqual(projection["groups"][0]["pending_count"], 2)
        self.assertTrue(projection["contracts"]["ai_priority_is_context_only"])
        self.assertFalse(projection["safety"]["automatic_execution"])

    def test_action_center_adds_one_low_review_task_and_suppresses_duplicate_optional_ai(self):
        campaign_id = "campaign_" + "e" * 24
        session = _session("ai_" + "5" * 24, created_at="2026-09-07T11:00:00+00:00", campaign_id=campaign_id, priority="HIGH")
        projection = project_recommendation_review("company_" + "f" * 24, sessions=[session], reviews=[])
        payload = extend_action_center(_base_action_center(campaign_id), projection)
        self.assertNotIn("optional_ai", {row["kind"] for row in payload["queue"]})
        rows = [row for row in payload["queue"] if row["source"] == "AI_REVIEW"]
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["rank"], 86)
        self.assertEqual(row["urgency"], "LOW")
        self.assertEqual(row["action"]["entity_id"], session["id"])
        self.assertEqual(row["action"]["tab"], "ai-recommendation-review")
        self.assertTrue(row["ai_context"]["priority_is_non_authoritative"])
        self.assertIn("HIGH", row["ai_context"]["suggested_priorities"])


class AIRecommendationReviewRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Astra Review"})
        self.campaign = self.runtime.campaigns.create(self.company["id"], {"name": "Campaña IA", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def _create_session(self, summary="Analizar"):
        context = {"schema": "test", "selected_campaign": {"name": self.campaign.name}, "privacy": {"contact_pii_included": False}}
        digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        return self.runtime.ai_sessions.create(
            self.company["id"], provider="ollama", model="llama3.2", task="CAMPAIGN", campaign_id=self.campaign.id,
            creative_media_id=None, instruction=None, context_sha256=digest, context=context,
            output={"summary": summary, "diagnosis": [], "recommendations": [{"title": "Probar CTA", "why": "Hipótesis para revisar", "priority": "HIGH", "area": "CAMPAIGN", "next_step": "Preparar variante"}], "creative_variants": [], "campaign_brief": {}}, provider_meta={},
        )

    def test_review_uses_server_side_identity_and_does_not_execute_business_action(self):
        self._create_session()
        projection = self.runtime.ai_recommendation_review(self.company["id"])
        rec = projection["groups"][0]["recommendations"][0]
        before_activities = list(self.runtime.crm.list_activities(self.company["id"]))
        result = self.runtime.review_ai_recommendation(self.company["id"], {"recommendation_id": rec["recommendation_id"], "decision": "ACCEPTED"})
        self.assertEqual(result["review"]["decision"], "ACCEPTED")
        self.assertFalse(result["reused"])
        self.assertEqual(result["projection"]["summary"]["pending_recommendations"], 0)
        self.assertEqual(list(self.runtime.crm.list_activities(self.company["id"])), before_activities)
        self.assertFalse(result["safety"]["provider_call_performed"])
        self.assertFalse(result["safety"]["business_execution_performed"])

    def test_old_unreviewed_recommendation_is_rejected_after_newer_session(self):
        self._create_session("Primera")
        old = self.runtime.ai_recommendation_review(self.company["id"])["groups"][0]["recommendations"][0]
        self._create_session("Segunda")
        with self.assertRaisesRegex(RecommendationReviewConflict, "no longer current"):
            self.runtime.review_ai_recommendation(self.company["id"], {"recommendation_id": old["recommendation_id"], "decision": "ACCEPTED"})
        self.assertEqual(self.runtime.ai_recommendation_reviews.list(self.company["id"]), [])

    def test_http_get_post_and_static_adapter(self):
        self._create_session()
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + f"/api/companies/{self.company['id']}/ai/recommendation-review", timeout=5) as response:
                projection = json.loads(response.read().decode("utf-8"))
            rec = projection["groups"][0]["recommendations"][0]
            with urlopen(root + "/ai-recommendation-review.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_AI_RECOMMENDATION_REVIEW", source)
            body = json.dumps({"recommendation_id": rec["recommendation_id"], "decision": "DISMISSED"}).encode("utf-8")
            request = Request(root + f"/api/companies/{self.company['id']}/ai/recommendation-review", data=body, method="POST", headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertEqual(result["review"]["decision"], "DISMISSED")
            self.assertEqual(result["projection"]["summary"]["pending_recommendations"], 0)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_contract_has_exact_transient_deep_link_and_only_explicit_review_mutation(self):
        source = (ROOT / "web" / "ai-recommendation-review.js").read_text(encoding="utf-8")
        for required in ("actionCenterOpen", "portfolioNavigate", "ai-recommendation-review", "dataset.aiReviewSessionId", "Aceptar recomendación", "Descartar", "window.confirm", "recommendation_id", "decision"):
            self.assertIn(required, source)
        self.assertEqual(source.count("method:'POST'"), 1)
        for forbidden in ("setInterval(", "setTimeout(", "MutationObserver", "localStorage", "sessionStorage", "sendBeacon", "fetch('https://", 'fetch("https://'):
            self.assertNotIn(forbidden, source)
        self.assertIn("priority del modelo no altera Hoy", source)
        self.assertIn("no publica, no activa pauta, no crea contenido y no modifica CRM", source)

    def test_source_contract_keeps_frozen_main_and_three_workflows(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_ai_recommendation_review_app", dev)
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_ai_recommendation_review_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_results_freshness_guard_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        docs = (ROOT / "docs" / "POST_W99_AI_RECOMMENDATION_REVIEW.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("no ejecuta", docs.lower())


if __name__ == "__main__":
    unittest.main()
