from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from binario_marketing.ai_human_feedback_context import (
    AI_HUMAN_FEEDBACK_CONTEXT_SCHEMA,
    MAX_FEEDBACK_ITEMS,
    project_ai_human_feedback_context,
)
from binario_marketing.ai_recommendation_handoff import RecommendationHandoffResolution
from binario_marketing.ai_recommendation_review import RecommendationReview, current_recommendations
from binario_marketing.service_post_w99_ai_human_feedback_context_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]
COMPANY_ID = "company_" + "b" * 24
CAMPAIGN_A = "campaign_" + "a" * 24
CAMPAIGN_B = "campaign_" + "c" * 24


def _session(session_id: str, *, campaign_id: str = CAMPAIGN_A, created_at: str = "2026-09-07T12:00:00+00:00", title: str = "Probar CTA") -> dict:
    return {
        "id": session_id,
        "task": "CAMPAIGN",
        "campaign_id": campaign_id,
        "creative_media_id": None,
        "created_at": created_at,
        "context": {"selected_campaign": {"name": "Campaña exacta"}},
        "output": {"recommendations": [{
            "title": title,
            "why": "Razonamiento anterior que no debe volver al proveedor como verdad.",
            "priority": "HIGH",
            "area": "CAMPAIGN",
            "next_step": "Siguiente paso anterior que tampoco debe reinyectarse.",
        }]},
    }


def _review(session: dict, decision: str) -> RecommendationReview:
    rec = current_recommendations([session])[0]
    return RecommendationReview(
        schema="binario.marketing.ai-recommendation-review.v1",
        company_id=COMPANY_ID,
        recommendation_id=rec["recommendation_id"],
        session_id=rec["session_id"],
        recommendation_sha256=rec["recommendation_sha256"],
        decision=decision,
        decided_at="2026-09-07T12:05:00+00:00",
    )


def _resolution(session: dict, outcome: str) -> RecommendationHandoffResolution:
    rec = current_recommendations([session])[0]
    return RecommendationHandoffResolution(
        schema="binario.marketing.ai-recommendation-handoff-resolution.v1",
        company_id=COMPANY_ID,
        recommendation_id=rec["recommendation_id"],
        session_id=rec["session_id"],
        recommendation_sha256=rec["recommendation_sha256"],
        outcome=outcome,
        resolved_at="2026-09-07T12:10:00+00:00",
    )


class AIHumanFeedbackPureTests(unittest.TestCase):
    def test_exact_target_only_and_unreviewed_output_is_omitted(self):
        reviewed = _session("ai_" + "1" * 24, campaign_id=CAMPAIGN_A)
        other_campaign = _session("ai_" + "2" * 24, campaign_id=CAMPAIGN_B, title="Otra campaña")
        unreviewed = _session("ai_" + "3" * 24, campaign_id=CAMPAIGN_A, title="Sin revisión")
        projection = project_ai_human_feedback_context(
            COMPANY_ID,
            task="CAMPAIGN",
            campaign_id=CAMPAIGN_A,
            creative_media_id=None,
            sessions=[unreviewed, other_campaign, reviewed],
            reviews=[_review(reviewed, "DISMISSED"), _review(other_campaign, "ACCEPTED")],
            resolutions=[],
            evidence={},
        )
        self.assertEqual(projection["schema"], AI_HUMAN_FEEDBACK_CONTEXT_SCHEMA)
        self.assertTrue(projection["scope"]["exact_target_only"])
        self.assertEqual(projection["summary"]["items"], 1)
        self.assertEqual(projection["items"][0]["historical_proposal"]["title"], "Probar CTA")
        self.assertEqual(projection["items"][0]["human_review"]["decision"], "DISMISSED")

    def test_prior_ai_rationale_and_next_step_are_not_reinjected(self):
        session = _session("ai_" + "4" * 24)
        projection = project_ai_human_feedback_context(
            COMPANY_ID,
            task="CAMPAIGN",
            campaign_id=CAMPAIGN_A,
            creative_media_id=None,
            sessions=[session],
            reviews=[_review(session, "ACCEPTED")],
            resolutions=[],
            evidence={},
        )
        serialized = json.dumps(projection, ensure_ascii=False)
        self.assertNotIn("Razonamiento anterior", serialized)
        self.assertNotIn("Siguiente paso anterior", serialized)
        self.assertFalse(projection["contracts"]["prior_rationale_included"])
        self.assertFalse(projection["contracts"]["prior_next_step_included"])
        self.assertTrue(projection["items"][0]["historical_proposal"]["is_prior_ai_output_not_verified_fact"])

    def test_human_outcome_and_evidence_remain_noncausal(self):
        session = _session("ai_" + "5" * 24)
        rec = current_recommendations([session])[0]
        projection = project_ai_human_feedback_context(
            COMPANY_ID,
            task="CAMPAIGN",
            campaign_id=CAMPAIGN_A,
            creative_media_id=None,
            sessions=[session],
            reviews=[_review(session, "ACCEPTED")],
            resolutions=[_resolution(session, "APPLIED")],
            evidence={"recommendations": [{"recommendation_id": rec["recommendation_id"], "state": "EVIDENCE_AVAILABLE"}]},
        )
        row = projection["items"][0]
        self.assertEqual(row["human_handoff"]["outcome"], "APPLIED")
        self.assertTrue(row["human_handoff"]["applied_is_not_business_execution_proof"])
        self.assertEqual(row["post_application_observation"]["state"], "EVIDENCE_AVAILABLE")
        self.assertFalse(row["post_application_observation"]["causal_attribution_to_ai"])
        self.assertFalse(projection["contracts"]["causal_attribution_to_ai"])
        self.assertTrue(projection["contracts"]["operator_feedback_is_not_performance_score"])

    def test_superseded_reviewed_sessions_remain_feedback_history(self):
        old = _session("ai_" + "6" * 24, created_at="2026-09-07T10:00:00+00:00", title="Idea anterior")
        new = _session("ai_" + "7" * 24, created_at="2026-09-07T11:00:00+00:00", title="Idea nueva")
        projection = project_ai_human_feedback_context(
            COMPANY_ID,
            task="CAMPAIGN",
            campaign_id=CAMPAIGN_A,
            creative_media_id=None,
            sessions=[new, old],
            reviews=[_review(new, "ACCEPTED"), _review(old, "DISMISSED")],
            resolutions=[],
            evidence={},
        )
        self.assertEqual([row["historical_proposal"]["title"] for row in projection["items"]], ["Idea nueva", "Idea anterior"])
        self.assertEqual(projection["summary"]["accepted"], 1)
        self.assertEqual(projection["summary"]["dismissed"], 1)

    def test_feedback_is_bounded(self):
        sessions = []
        reviews = []
        for index in range(MAX_FEEDBACK_ITEMS + 5):
            session = _session(f"ai_{index:024x}", created_at=f"2026-09-07T{index % 24:02d}:00:00+00:00", title=f"Idea {index}")
            sessions.append(session)
            reviews.append(_review(session, "DISMISSED"))
        projection = project_ai_human_feedback_context(
            COMPANY_ID,
            task="CAMPAIGN",
            campaign_id=CAMPAIGN_A,
            creative_media_id=None,
            sessions=sessions,
            reviews=reviews,
            resolutions=[],
            evidence={},
        )
        self.assertEqual(len(projection["items"]), MAX_FEEDBACK_ITEMS)


class AIHumanFeedbackRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Astra Feedback"})
        self.campaign = self.runtime.campaigns.create(
            self.company["id"],
            {"name": "Campaña Feedback", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]},
        )

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def _create_reviewed_session(self, decision: str = "DISMISSED"):
        context = {"schema": "test", "selected_campaign": {"name": self.campaign.name}, "privacy": {"contact_pii_included": False}}
        digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        session = self.runtime.ai_sessions.create(
            self.company["id"],
            provider="ollama",
            model="llama3.2",
            task="CAMPAIGN",
            campaign_id=self.campaign.id,
            creative_media_id=None,
            instruction=None,
            context_sha256=digest,
            context=context,
            output={
                "summary": "Histórica",
                "diagnosis": [],
                "recommendations": [{
                    "title": "Repetir oferta",
                    "why": "Texto previo",
                    "priority": "HIGH",
                    "area": "CAMPAIGN",
                    "next_step": "Paso previo",
                }],
                "creative_variants": [],
                "campaign_brief": {},
            },
            provider_meta={},
        )
        rec = current_recommendations([session])[0]
        self.runtime.ai_recommendation_reviews.record(
            self.company["id"],
            recommendation=rec["recommendation_id"],
            session_id=rec["session_id"],
            digest=rec["recommendation_sha256"],
            decision=decision,
        )
        return session, rec

    def test_runtime_ai_context_includes_feedback_and_preserves_privacy_contract(self):
        self._create_reviewed_session("DISMISSED")
        context = self.runtime._ai_context(
            self.company["id"],
            task="CAMPAIGN",
            campaign_id=self.campaign.id,
            creative_media_id=None,
        )
        feedback = context["human_recommendation_feedback"]
        self.assertEqual(feedback["summary"]["dismissed"], 1)
        self.assertTrue(feedback["contracts"]["human_review_required_for_feedback_item"])
        self.assertFalse(context["privacy"]["contact_pii_included"])
        self.assertTrue(context["privacy"]["historical_reviewed_ai_proposals_included"])
        self.assertFalse(context["privacy"]["historical_ai_rationale_included"])
        self.assertFalse(context["privacy"]["historical_ai_next_step_included"])

    def test_explicit_generation_persists_feedback_context_without_real_provider(self):
        self._create_reviewed_session("DISMISSED")
        self.runtime.ai_settings.update(self.company["id"], {"provider": "ollama", "model": "llama3.2"})

        calls = []

        class FakeAIClient:
            def generate(_self, provider, model, *, system, prompt):
                calls.append({"provider": provider, "model": model, "system": system, "prompt": prompt})
                return SimpleNamespace(
                    provider=provider,
                    model=model,
                    output={
                        "summary": "Nueva sesión",
                        "diagnosis": [],
                        "recommendations": [],
                        "creative_variants": [],
                        "campaign_brief": {},
                    },
                    provider_meta={"transport": "fake"},
                )

        self.runtime.ai_client = FakeAIClient()
        generated = self.runtime.generate_ai_copilot(
            self.company["id"],
            {"task": "CAMPAIGN", "campaign_id": self.campaign.id},
        )
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["provider"], "ollama")
        feedback = generated["context"]["human_recommendation_feedback"]
        self.assertEqual(feedback["summary"]["dismissed"], 1)
        self.assertEqual(feedback["items"][0]["historical_proposal"]["title"], "Repetir oferta")
        self.assertNotIn("Texto previo", json.dumps(feedback, ensure_ascii=False))
        persisted = self.runtime.ai_sessions.list(self.company["id"], limit=1)[0]
        self.assertEqual(persisted.id, generated["id"])
        self.assertEqual(persisted.context["human_recommendation_feedback"]["summary"]["dismissed"], 1)

    def test_prompt_explicitly_blocks_self_validation_and_mechanical_repetition(self):
        system, prompt = self.runtime._ai_prompt(
            task="CAMPAIGN",
            context={"human_recommendation_feedback": {"items": []}},
            instruction=None,
            language="es",
            brand_voice="",
        )
        self.assertIn("untrusted prior model output", system)
        self.assertIn("APPLIED does not prove execution", system)
        self.assertIn("later evidence does not prove causality", system)
        self.assertIn("Do not mechanically repeat", system)
        self.assertIn("Do not automatically prefer or prioritize ACCEPTED or APPLIED", system)
        self.assertIn("human_recommendation_feedback", prompt)

    def test_source_bundle_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_ai_human_feedback_context_app", dev)
        core = (ROOT / "src" / "binario_marketing" / "ai_human_feedback_context.py").read_text(encoding="utf-8")
        self.assertIn("MAX_FEEDBACK_ITEMS = 12", core)
        self.assertIn("prior_ai_text_is_untrusted_history", core)
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_ai_human_feedback_context_app.py").read_text(encoding="utf-8")
        self.assertIn("human_recommendation_feedback", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        build = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        for source in (build, audit, smoke):
            self.assertIn("ai_human_feedback_context", source)
        self.assertIn("MAX_FEEDBACK_ITEMS = 12", audit)
        self.assertIn("service_post_w99_ai_human_feedback_context_app", smoke)
        docs = (ROOT / "docs" / "POST_W99_AI_HUMAN_FEEDBACK_CONTEXT.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("no causal", docs.casefold())


if __name__ == "__main__":
    unittest.main()
