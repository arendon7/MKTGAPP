from __future__ import annotations

import hashlib
import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.ai_recommendation_evidence import (
    FOLLOWUP_WINDOW_SECONDS,
    extend_action_center,
    project_recommendation_evidence,
)
from binario_marketing.ai_recommendation_handoff import RecommendationHandoffResolution
from binario_marketing.ai_recommendation_review import current_recommendations
from binario_marketing.service_post_w99_ai_recommendation_evidence_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
COMPANY_ID = "company_" + "b" * 24
CAMPAIGN_ID = "campaign_" + "a" * 24
OTHER_CAMPAIGN_ID = "campaign_" + "c" * 24
MEDIA_ID = "media_" + "d" * 24


def _session(
    session_id: str,
    *,
    created_at: str = "2026-09-07T12:00:00+00:00",
    task: str = "CAMPAIGN",
    campaign_id: str | None = CAMPAIGN_ID,
    creative_media_id: str | None = None,
    area: str = "CAMPAIGN",
    title: str = "Probar una mejora",
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
            "why": "Hipótesis para revisar con evidencia.",
            "priority": "HIGH",
            "area": area,
            "next_step": "Aplicar manualmente en el owner.",
        }]},
    }


def _resolution(session: dict, *, applied_at: str = "2026-09-07T13:00:00+00:00", outcome: str = "APPLIED") -> RecommendationHandoffResolution:
    rec = current_recommendations([session])[0]
    return RecommendationHandoffResolution(
        schema="binario.marketing.ai-recommendation-handoff-resolution.v1",
        company_id=COMPANY_ID,
        recommendation_id=rec["recommendation_id"],
        session_id=rec["session_id"],
        recommendation_sha256=rec["recommendation_sha256"],
        outcome=outcome,
        resolved_at=applied_at,
    )


def _snapshot(
    snapshot_id: str,
    *,
    created_at: str,
    campaign_id: str = CAMPAIGN_ID,
    media_id: str | None = None,
    metrics: dict | None = None,
) -> dict:
    return {
        "id": snapshot_id,
        "company_id": COMPANY_ID,
        "date_preset": "last_7d",
        "created_at": created_at,
        "social": {
            "observations": [{
                "publication_id": "pub_1",
                "channel": "instagram",
                "campaign_id": campaign_id,
                "creative_media_id": media_id,
                "metrics": metrics or {},
            }]
        },
        "paid_media": {"observations": []},
        "crm": {},
        "coverage": {},
    }


def _base_action_center(*, capture_campaign: str | None = None) -> dict:
    queue = []
    if capture_campaign:
        queue.append({
            "id": "CAMPAIGN:capture:test",
            "rank": 44,
            "urgency": "MEDIUM",
            "source": "CAMPAIGN",
            "kind": "capture_results",
            "title": "Actualizar resultados",
            "detail": "Captura existente",
            "action": {"label": "Actualizar resultados", "view": "analytics", "tab": None, "entity_id": None, "lead_id": None, "contact_id": None, "opportunity_id": None, "campaign_id": capture_campaign, "media_id": None},
            "reason": {"code": "CAMPAIGN_CAPTURE_RESULTS", "explanation": "Ya existe"},
            "due_at": None,
            "blocking": False,
            "requires_human_action": True,
            "read_only_recommendation": True,
        })
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": COMPANY_ID, "name": "Empresa"},
        "queue": queue,
        "next_action": queue[0] if queue else None,
        "focus": {"now": [], "next": list(queue), "later": []},
        "summary": {"queue_total": len(queue), "blocking": 0, "critical": 0, "high": 0, "medium": len(queue), "low": 0, "by_source": {"CAMPAIGN": len(queue)} if queue else {}},
        "contracts": {},
        "safety": {},
    }


class AIRecommendationEvidencePureTests(unittest.TestCase):
    def test_applied_recommendation_survives_newer_ai_session_for_same_target(self):
        old = _session("ai_" + "1" * 24, title="Recomendación histórica")
        new = _session("ai_" + "2" * 24, created_at="2026-09-07T14:00:00+00:00", title="Recomendación nueva")
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[new, old],
            resolutions=[_resolution(old)],
            snapshots=[],
            now=datetime(2026, 9, 7, 14, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(evidence["summary"]["tracked_applied"], 1)
        self.assertEqual(evidence["recommendations"][0]["title"], "Recomendación histórica")
        self.assertEqual(evidence["recommendations"][0]["state"], "OBSERVATION_WINDOW")

    def test_exact_post_application_campaign_signal_becomes_observational_evidence(self):
        session = _session("ai_" + "3" * 24)
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[_resolution(session)],
            snapshots=[_snapshot("learning_" + "1" * 24, created_at="2026-09-07T15:00:00+00:00", metrics={"reach": 120, "comments": 4})],
            now=datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc),
        )
        row = evidence["recommendations"][0]
        self.assertEqual(row["state"], "EVIDENCE_AVAILABLE")
        self.assertEqual(row["post_application_snapshot"]["organic_observations"], 1)
        self.assertEqual(row["post_application_snapshot"]["organic_samples"][0]["metrics"]["reach"], 120)
        self.assertFalse(row["causal_attribution"])
        self.assertFalse(evidence["contracts"]["causal_attribution_to_ai"])

    def test_other_campaign_snapshot_does_not_count_as_exact_target_signal(self):
        session = _session("ai_" + "4" * 24)
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[_resolution(session)],
            snapshots=[_snapshot("learning_" + "2" * 24, created_at="2026-09-07T15:00:00+00:00", campaign_id=OTHER_CAMPAIGN_ID, metrics={"reach": 999})],
            now=datetime(2026, 9, 7, 16, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(evidence["recommendations"][0]["state"], "POST_SNAPSHOT_NO_TARGET_SIGNAL")
        self.assertEqual(evidence["recommendations"][0]["post_snapshots_with_target_signal"], 0)

    def test_creative_followup_requires_exact_media_identity(self):
        session = _session(
            "ai_" + "5" * 24,
            task="CREATIVE",
            campaign_id=CAMPAIGN_ID,
            creative_media_id=MEDIA_ID,
            area="CONTENT",
        )
        wrong = _snapshot("learning_" + "3" * 24, created_at="2026-09-07T15:00:00+00:00", campaign_id=CAMPAIGN_ID, media_id="media_" + "e" * 24, metrics={"views": 20})
        right = _snapshot("learning_" + "4" * 24, created_at="2026-09-07T16:00:00+00:00", campaign_id=CAMPAIGN_ID, media_id=MEDIA_ID, metrics={"views": 30})
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[_resolution(session)],
            snapshots=[right, wrong],
            now=datetime(2026, 9, 7, 17, 0, tzinfo=timezone.utc),
        )
        row = evidence["recommendations"][0]
        self.assertEqual(row["target"]["kind"], "CREATIVE")
        self.assertEqual(row["target"]["id"], MEDIA_ID)
        self.assertEqual(row["post_application_snapshot"]["snapshot_id"], right["id"])

    def test_24h_without_post_snapshot_creates_capture_due(self):
        session = _session("ai_" + "6" * 24)
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[_resolution(session, applied_at="2026-09-06T12:00:00+00:00")],
            snapshots=[],
            now=datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
        )
        row = evidence["recommendations"][0]
        self.assertEqual(row["state"], "CAPTURE_DUE")
        self.assertGreaterEqual(row["age_seconds"], FOLLOWUP_WINDOW_SECONDS)

    def test_not_applied_never_enters_post_application_tracking(self):
        session = _session("ai_" + "7" * 24)
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[_resolution(session, outcome="NOT_APPLIED")],
            snapshots=[],
            now=datetime(2026, 9, 8, 13, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(evidence["summary"]["tracked_applied"], 0)
        self.assertEqual(evidence["summary"]["not_applied"], 1)
        self.assertEqual(evidence["recommendations"], [])

    def test_action_center_adds_one_low_capture_due_task(self):
        session = _session("ai_" + "8" * 24)
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[_resolution(session, applied_at="2026-09-06T12:00:00+00:00")],
            snapshots=[],
            now=datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
        )
        result = extend_action_center(_base_action_center(), evidence)
        rows = [row for row in result["queue"] if row.get("source") == "AI_EVIDENCE"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["rank"], 88)
        self.assertEqual(rows[0]["urgency"], "LOW")
        self.assertEqual(rows[0]["action"]["view"], "analytics")
        self.assertFalse(result["safety"]["ai_evidence_causal_attribution"])

    def test_existing_campaign_capture_results_shadows_ai_duplicate(self):
        session = _session("ai_" + "9" * 24)
        evidence = project_recommendation_evidence(
            COMPANY_ID,
            sessions=[session],
            resolutions=[_resolution(session, applied_at="2026-09-06T12:00:00+00:00")],
            snapshots=[],
            now=datetime(2026, 9, 7, 13, 0, tzinfo=timezone.utc),
        )
        result = extend_action_center(_base_action_center(capture_campaign=CAMPAIGN_ID), evidence)
        self.assertFalse(any(row.get("source") == "AI_EVIDENCE" for row in result["queue"]))
        self.assertEqual(result["summary"]["ai_evidence_capture_shadowed"], 1)


class AIRecommendationEvidenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Astra Evidence"})
        self.campaign = self.runtime.campaigns.create(self.company["id"], {"name": "Campaña Evidence", "objective": "LEADS", "status": "IN_PROGRESS", "channels": ["instagram"]})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def _create_applied(self):
        context = {"schema": "test", "selected_campaign": {"name": self.campaign.name}, "privacy": {"contact_pii_included": False}}
        digest = hashlib.sha256(json.dumps(context, sort_keys=True).encode()).hexdigest()
        self.runtime.ai_sessions.create(
            self.company["id"], provider="ollama", model="llama3.2", task="CAMPAIGN", campaign_id=self.campaign.id,
            creative_media_id=None, instruction=None, context_sha256=digest, context=context,
            output={"summary": "Analizar", "diagnosis": [], "recommendations": [{"title": "Probar CTA", "why": "Hipótesis", "priority": "HIGH", "area": "CAMPAIGN", "next_step": "Aplicar manualmente"}], "creative_variants": [], "campaign_brief": {}}, provider_meta={},
        )
        review = self.runtime.ai_recommendation_review(self.company["id"])
        rec = review["groups"][0]["recommendations"][0]
        self.runtime.review_ai_recommendation(self.company["id"], {"recommendation_id": rec["recommendation_id"], "decision": "ACCEPTED"})
        self.runtime.resolve_ai_recommendation_handoff(self.company["id"], {"recommendation_id": rec["recommendation_id"], "outcome": "APPLIED"})
        return rec

    def test_learning_payload_embeds_noncausal_followup(self):
        rec = self._create_applied()
        payload = self.runtime.learning_payload(self.company["id"])
        follow = payload["ai_recommendation_followup"]
        self.assertEqual(follow["summary"]["tracked_applied"], 1)
        self.assertEqual(follow["recommendations"][0]["recommendation_id"], rec["recommendation_id"])
        self.assertFalse(payload["attribution"]["ai_recommendation_causal_attribution"])
        self.assertTrue(payload["safety"]["ai_recommendation_followup_read_only"])

    def test_post_snapshot_with_exact_metrics_appears_after_manual_capture_only(self):
        self._create_applied()
        self.runtime.learning.create_snapshot(self.company["id"], {
            "date_preset": "last_7d",
            "social": {"configured": False, "coverage": {}, "totals": {}, "observations": [{"publication_id": "pub_runtime", "channel": "instagram", "campaign_id": self.campaign.id, "creative_media_id": None, "metrics": {"reach": 77}, "available": True, "provider_error": False}]},
            "paid_media": {"coverage": {}, "currencies": [], "spend_aggregated": True, "totals": {}, "totals_by_currency": {}, "observations": []},
            "crm": {},
            "coverage": {},
        })
        evidence = self.runtime.ai_recommendation_evidence(self.company["id"])
        self.assertEqual(evidence["recommendations"][0]["state"], "EVIDENCE_AVAILABLE")
        self.assertEqual(evidence["recommendations"][0]["post_application_snapshot"]["organic_samples"][0]["metrics"]["reach"], 77)
        self.assertFalse(evidence["safety"]["provider_read_performed"])

    def test_http_projection_and_static_asset_are_get_only(self):
        self._create_applied()
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + f"/api/companies/{self.company['id']}/ai/recommendation-evidence", timeout=5) as response:
                projection = json.loads(response.read().decode("utf-8"))
            self.assertEqual(projection["summary"]["tracked_applied"], 1)
            with urlopen(root + "/ai-recommendation-evidence.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_AI_RECOMMENDATION_EVIDENCE", source)
            self.assertNotIn("method:'POST'", source)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_contract_has_no_provider_or_mutation_authority(self):
        source = (ROOT / "web" / "ai-recommendation-evidence.js").read_text(encoding="utf-8")
        for required in ("recommendation-evidence", "Evidencia posterior disponible", "Abrir Resultados para actualizar", "causalidad", "actionCenterOpen", "portfolioNavigate"):
            self.assertIn(required, source)
        for forbidden in ("method:'POST'", "setInterval(", "setTimeout(", "MutationObserver", "localStorage", "sessionStorage", "sendBeacon", ".click()", "fetch('https://", 'fetch("https://'):
            self.assertNotIn(forbidden, source)

    def test_source_bundle_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_ai_recommendation_evidence_app", dev)
        build = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("ai_recommendation_evidence.py", build)
        self.assertIn("ai-recommendation-evidence.js", build)
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_ai_recommendation_evidence_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_ai_recommendation_handoff_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        docs = (ROOT / "docs" / "POST_W99_AI_RECOMMENDATION_EVIDENCE_FOLLOWUP.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("no demuestra causalidad", docs.casefold())


if __name__ == "__main__":
    unittest.main()
