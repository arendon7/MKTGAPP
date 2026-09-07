from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.ai_recommendation_handoff import (
    RecommendationHandoffConflict,
    RecommendationHandoffStore,
    extend_action_center,
    project_recommendation_handoffs,
)
from binario_marketing.ai_recommendation_review import RecommendationReview, current_recommendations
from binario_marketing.service_post_w99_ai_recommendation_handoff_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def _session(
    session_id: str,
    *,
    created_at: str = "2026-09-07T15:00:00+00:00",
    task: str = "CAMPAIGN",
    campaign_id: str | None = "campaign_" + "a" * 24,
    creative_media_id: str | None = None,
    area: str = "CAMPAIGN",
    title: str = "Ajustar estrategia",
) -> dict:
    return {
        "id": session_id,
        "task": task,
        "campaign_id": campaign_id,
        "creative_media_id": creative_media_id,
        "created_at": created_at,
        "context": {"selected_campaign": {"name": "Campaña exacta"}, "selected_creative": {"title": "Creativo exacto"}},
        "output": {"recommendations": [{
            "title": title,
            "why": "La evidencia sugiere revisar el siguiente paso.",
            "priority": "HIGH",
            "area": area,
            "next_step": "Aplicar manualmente desde el módulo propietario.",
        }]},
    }


def _accepted(session: dict) -> RecommendationReview:
    rec = current_recommendations([session])[0]
    return RecommendationReview(
        schema="binario.marketing.ai-recommendation-review.v1",
        company_id="company_" + "b" * 24,
        recommendation_id=rec["recommendation_id"],
        session_id=rec["session_id"],
        recommendation_sha256=rec["recommendation_sha256"],
        decision="ACCEPTED",
        decided_at="2026-09-07T15:05:00+00:00",
    )


def _base_action_center() -> dict:
    existing = {
        "id": "SETUP:existing:test", "rank": 82, "urgency": "LOW", "source": "SETUP", "kind": "existing",
        "title": "Configuración existente", "detail": "No debe reordenarse por IA", "action": {"label": "Abrir", "view": "companies", "tab": None, "entity_id": None, "lead_id": None, "contact_id": None, "opportunity_id": None, "campaign_id": None, "media_id": None},
        "reason": {"code": "SETUP_EXISTING", "explanation": "Existente"}, "due_at": None, "blocking": False,
        "requires_human_action": True, "read_only_recommendation": True,
    }
    return {
        "schema": "binario.marketing.action-center.v1", "company": {"id": "company_" + "b" * 24, "name": "Empresa"},
        "queue": [existing], "next_action": existing, "focus": {"now": [], "next": [], "later": [existing]},
        "summary": {"queue_total": 1, "blocking": 0, "critical": 0, "high": 0, "medium": 0, "low": 1, "by_source": {"SETUP": 1}},
        "contracts": {}, "safety": {},
    }


class AIRecommendationHandoffPureTests(unittest.TestCase):
    def test_campaign_strategy_routes_only_from_structured_identity(self):
        session = _session("ai_" + "1" * 24, area="CAMPAIGN", title="Texto libre irrelevante sobre CRM")
        projection = project_recommendation_handoffs("company_" + "b" * 24, sessions=[session], reviews=[_accepted(session)], resolutions=[])
        self.assertEqual(projection["summary"]["open_handoffs"], 1)
        route = projection["handoffs"][0]["route"]
        self.assertEqual(route["view"], "campaigns")
        self.assertEqual(route["campaign_id"], session["campaign_id"])
        self.assertTrue(projection["contracts"]["owner_from_structured_fields_only"])
        self.assertFalse(projection["contracts"]["free_text_owner_inference"])

    def test_crm_area_without_exact_crm_entity_fails_closed_as_owner_gap(self):
        session = _session("ai_" + "2" * 24, area="CRM", title="Crear seguimiento para Juan")
        projection = project_recommendation_handoffs("company_" + "b" * 24, sessions=[session], reviews=[_accepted(session)], resolutions=[])
        self.assertEqual(projection["summary"]["open_handoffs"], 0)
        self.assertEqual(projection["summary"]["owner_gaps"], 1)
        self.assertEqual(projection["owner_gaps"][0]["route"]["state"], "OWNER_GAP")

    def test_creative_content_requires_exact_media_and_routes_to_content(self):
        session = _session(
            "ai_" + "3" * 24,
            task="CREATIVE",
            campaign_id="campaign_" + "c" * 24,
            creative_media_id="media_" + "d" * 24,
            area="CONTENT",
        )
        projection = project_recommendation_handoffs("company_" + "b" * 24, sessions=[session], reviews=[_accepted(session)], resolutions=[])
        route = projection["handoffs"][0]["route"]
        self.assertEqual(route["view"], "content")
        self.assertEqual(route["media_id"], session["creative_media_id"])

    def test_only_current_accepted_recommendation_can_be_open_handoff(self):
        old = _session("ai_" + "4" * 24, created_at="2026-09-07T14:00:00+00:00", title="Vieja")
        new = _session("ai_" + "5" * 24, created_at="2026-09-07T15:00:00+00:00", title="Nueva")
        projection = project_recommendation_handoffs("company_" + "b" * 24, sessions=[new, old], reviews=[_accepted(old), _accepted(new)], resolutions=[])
        self.assertEqual(len(projection["handoffs"]), 1)
        self.assertEqual(projection["handoffs"][0]["title"], "Nueva")

    def test_store_is_idempotent_and_outcome_change_conflicts(self):
        session = _session("ai_" + "6" * 24)
        rec = current_recommendations([session])[0]
        with tempfile.TemporaryDirectory() as tmp:
            store = RecommendationHandoffStore(Path(tmp))
            first = store.record("company_" + "b" * 24, recommendation_id=rec["recommendation_id"], session_id=rec["session_id"], digest=rec["recommendation_sha256"], outcome="APPLIED")
            second = store.record("company_" + "b" * 24, recommendation_id=rec["recommendation_id"], session_id=rec["session_id"], digest=rec["recommendation_sha256"], outcome="APPLIED")
            self.assertEqual(first, second)
            with self.assertRaises(RecommendationHandoffConflict):
                store.record("company_" + "b" * 24, recommendation_id=rec["recommendation_id"], session_id=rec["session_id"], digest=rec["recommendation_sha256"], outcome="NOT_APPLIED")

    def test_action_center_adds_low_owner_handoff_without_changing_higher_order(self):
        session = _session("ai_" + "7" * 24)
        projection = project_recommendation_handoffs("company_" + "b" * 24, sessions=[session], reviews=[_accepted(session)], resolutions=[])
        result = extend_action_center(_base_action_center(), projection)
        rows = [row for row in result["queue"] if row.get("source") == "AI_HANDOFF"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rank"], 87)
        self.assertEqual(rows[0]["urgency"], "LOW")
        self.assertEqual(rows[0]["action"]["view"], "campaigns")
        self.assertEqual(rows[0]["action"]["entity_id"], projection["handoffs"][0]["recommendation_id"])
        self.assertLess(result["queue"].index(_base_action_center()["queue"][0]), result["queue"].index(rows[0]))
        self.assertFalse(result["safety"]["ai_handoff_executes_business_action"])


class AIRecommendationHandoffRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Astra Handoff"})
        self.campaign = self.runtime.campaigns.create(self.company["id"], {"name": "Campaña Handoff", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def _create_session(self, *, summary="Analizar", area="CAMPAIGN"):
        context = {"schema": "test", "selected_campaign": {"name": self.campaign.name}, "privacy": {"contact_pii_included": False}}
        digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        return self.runtime.ai_sessions.create(
            self.company["id"], provider="ollama", model="llama3.2", task="CAMPAIGN", campaign_id=self.campaign.id,
            creative_media_id=None, instruction=None, context_sha256=digest, context=context,
            output={"summary": summary, "diagnosis": [], "recommendations": [{"title": "Probar CTA", "why": "Hipótesis para revisar", "priority": "HIGH", "area": area, "next_step": "Abrir campaña y aplicar manualmente"}], "creative_variants": [], "campaign_brief": {}}, provider_meta={},
        )

    def _accept_current(self):
        projection = self.runtime.ai_recommendation_review(self.company["id"])
        rec = projection["groups"][0]["recommendations"][0]
        self.runtime.review_ai_recommendation(self.company["id"], {"recommendation_id": rec["recommendation_id"], "decision": "ACCEPTED"})
        return rec

    def test_acceptance_creates_handoff_projection_but_no_business_execution(self):
        self._create_session(); rec = self._accept_current()
        before_campaign = self.runtime.campaigns.get(self.campaign.id)
        handoffs = self.runtime.ai_recommendation_handoffs(self.company["id"])
        self.assertEqual(handoffs["summary"]["open_handoffs"], 1)
        self.assertEqual(handoffs["handoffs"][0]["recommendation_id"], rec["recommendation_id"])
        self.assertFalse(handoffs["safety"]["business_mutation_performed"])
        after_campaign = self.runtime.campaigns.get(self.campaign.id)
        self.assertEqual(before_campaign, after_campaign)

    def test_manual_resolution_closes_handoff_without_executing_marketing(self):
        self._create_session(); rec = self._accept_current()
        before_activities = list(self.runtime.crm.list_activities(self.company["id"]))
        result = self.runtime.resolve_ai_recommendation_handoff(self.company["id"], {"recommendation_id": rec["recommendation_id"], "outcome": "APPLIED"})
        self.assertEqual(result["resolution"]["outcome"], "APPLIED")
        self.assertFalse(result["reused"])
        self.assertEqual(result["projection"]["summary"]["open_handoffs"], 0)
        self.assertEqual(result["projection"]["summary"]["applied_current"], 1)
        self.assertEqual(list(self.runtime.crm.list_activities(self.company["id"])), before_activities)
        self.assertFalse(result["safety"]["provider_call_performed"])
        self.assertFalse(result["safety"]["business_execution_performed"])

    def test_owner_gap_cannot_be_resolved_as_handoff(self):
        self._create_session(area="CRM"); rec = self._accept_current()
        projection = self.runtime.ai_recommendation_handoffs(self.company["id"])
        self.assertEqual(projection["summary"]["owner_gaps"], 1)
        with self.assertRaises(RecommendationHandoffConflict):
            self.runtime.resolve_ai_recommendation_handoff(self.company["id"], {"recommendation_id": rec["recommendation_id"], "outcome": "APPLIED"})

    def test_superseded_unresolved_handoff_is_rejected(self):
        self._create_session(summary="Primera"); old = self._accept_current()
        self._create_session(summary="Segunda")
        with self.assertRaises(RecommendationHandoffConflict):
            self.runtime.resolve_ai_recommendation_handoff(self.company["id"], {"recommendation_id": old["recommendation_id"], "outcome": "APPLIED"})

    def test_http_get_post_and_static_asset(self):
        self._create_session(); rec = self._accept_current()
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + f"/api/companies/{self.company['id']}/ai/recommendation-handoffs", timeout=5) as response:
                projection = json.loads(response.read().decode("utf-8"))
            self.assertEqual(projection["summary"]["open_handoffs"], 1)
            with urlopen(root + "/ai-recommendation-handoff.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_AI_RECOMMENDATION_HANDOFF", source)
            body = json.dumps({"recommendation_id": rec["recommendation_id"], "outcome": "NOT_APPLIED"}).encode("utf-8")
            request = Request(root + f"/api/companies/{self.company['id']}/ai/recommendation-handoffs", data=body, method="POST", headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertEqual(result["resolution"]["outcome"], "NOT_APPLIED")
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_contract_is_transient_explicit_and_does_not_execute_owner_controls(self):
        source = (ROOT / "web" / "ai-recommendation-handoff.js").read_text(encoding="utf-8")
        for required in ("ai-accepted-handoff", "actionCenterOpen", "portfolioNavigate", "Abrir módulo responsable", "Marcar aplicada", "No aplicar", "window.confirm", "recommendation_id", "outcome", "dataset.aiHandoffRecommendationId"):
            self.assertIn(required, source)
        self.assertIn("action?.tab==='ai-accepted-handoff'", source)
        self.assertEqual(source.count("method:'POST'"), 1)
        for forbidden in ("setInterval(", "setTimeout(", "MutationObserver", "localStorage", "sessionStorage", "sendBeacon", ".click()", "fetch('https://", 'fetch("https://'):
            self.assertNotIn(forbidden, source)

    def test_source_bundle_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_ai_recommendation_handoff_app", dev)
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_ai_recommendation_handoff_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_ai_recommendation_review_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        builder = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        for source in (builder, audit, smoke):
            self.assertIn("ai_recommendation_handoff", source)
        self.assertIn("recommendation_handoffs", smoke)
        docs = (ROOT / "docs" / "POST_W99_AI_ACCEPTED_OWNER_HANDOFF.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("never chooses an owner", docs.lower())
        self.assertIn("does not execute recommendations", docs.lower())


if __name__ == "__main__":
    unittest.main()
