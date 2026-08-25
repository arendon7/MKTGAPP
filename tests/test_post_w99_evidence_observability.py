import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_evidence_observability_app import (
    AppRuntime,
    compose_evidence_observability,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]
AS_OF = "2026-08-24T20:00:00+00:00"


def results(*, snapshot=True, signal=True, observed=True):
    row = {
        "campaign": {"id": "camp-1", "name": "Campaña 1", "status": "ACTIVE"},
        "evidence": {"has_signal": signal, "observed": observed},
        "attribution": {"attributed_opportunities": 1 if signal else 0},
    }
    return {
        "latest_snapshot": ({
            "id": "snap-1",
            "created_at": "2026-08-24T18:00:00+00:00",
            "date_preset": "last_7d",
            "coverage": {"campaigns": 1},
        } if snapshot else None),
        "summary": {"campaigns": 1, "active_campaigns": 1},
        "campaigns": [row],
    }


def outcomes(*, links=1, leads=1, opportunities=1, won=0):
    return {
        "summary": {
            "tracking_links": links,
            "captured_leads": leads,
            "captured_touches": leads,
            "attributed_opportunities": opportunities,
            "attributed_won": won,
        },
        "campaigns": [{
            "campaign": {"id": "camp-1", "name": "Campaña 1"},
            "journeys": ([{"lead_id": "lead-1", "received_at": "2026-08-24T19:00:00+00:00"}] if leads else []),
        }],
    }


def review(*, with_post=True):
    post = {
        "basis": (["OBSERVED_MARKETING_SNAPSHOT"] if with_post else []),
        "observed_marketing": ({"created_at": "2026-08-24T19:30:00+00:00"} if with_post else None),
        "attributed_crm_updates": [],
        "campaign_terminal_after_decision": False,
    }
    return {
        "summary": {
            "ready_for_review": 1 if with_post else 0,
            "follow_through_required": 0,
            "awaiting_evidence": 0 if with_post else 1,
        },
        "campaigns": [{
            "campaign": {"id": "camp-1", "name": "Campaña 1", "updated_at": "2026-08-24T19:40:00+00:00"},
            "decision": {"id": "dec-1", "created_at": "2026-08-24T17:00:00+00:00"},
            "post_decision_evidence": post,
        }],
    }


class EvidenceProjectionTests(unittest.TestCase):
    def test_observed_domains_expose_age_without_fresh_or_stale_judgment(self):
        payload = compose_evidence_observability(
            company={"id": "c1", "name": "Empresa"},
            results=results(), outcomes=outcomes(), review=review(), projected_at=AS_OF,
        )
        self.assertEqual(payload["schema"], "binario.marketing.evidence-observability.v1")
        self.assertEqual(payload["summary"], {
            "domains": 4, "observed": 4, "partial": 0, "not_observed": 0, "unknown": 0,
        })
        snapshot = payload["domains"][0]
        self.assertEqual(snapshot["freshness"]["age_seconds"], 7200)
        self.assertEqual(snapshot["freshness"]["classification"], "AGE_OBSERVED")
        self.assertIsNone(snapshot["freshness"]["fresh"])
        self.assertIsNone(snapshot["freshness"]["stale"])
        self.assertEqual(snapshot["freshness"]["policy"], "NO_STALENESS_THRESHOLD_CONFIGURED")
        self.assertTrue(payload["contracts"]["age_is_measurement_not_freshness_judgment"])
        self.assertTrue(payload["contracts"]["no_staleness_threshold_configured"])

    def test_instrumentation_without_capture_is_partial_not_zero_performance(self):
        payload = compose_evidence_observability(
            company={"id": "c1", "name": "Empresa"},
            results=results(signal=False, observed=False),
            outcomes=outcomes(links=2, leads=0, opportunities=0),
            review=review(with_post=False),
            projected_at=AS_OF,
        )
        by_key = {row["key"]: row for row in payload["domains"]}
        commercial = by_key["COMMERCIAL_ATTRIBUTION"]
        self.assertEqual(commercial["status"], "PARTIAL")
        self.assertEqual(commercial["coverage"]["tracking_links"], 2)
        self.assertEqual(commercial["coverage"]["captured_leads"], 0)
        self.assertTrue(any("no equivale a cero" in text.lower() for text in commercial["caveats"]))
        campaign = by_key["CAMPAIGN_EVIDENCE"]
        self.assertEqual(campaign["status"], "NOT_OBSERVED")
        self.assertTrue(payload["contracts"]["absence_is_not_zero_performance"])

    def test_no_snapshot_with_campaign_is_not_observed_not_failed(self):
        payload = compose_evidence_observability(
            company={"id": "c1", "name": "Empresa"},
            results=results(snapshot=False, signal=False, observed=False),
            outcomes=outcomes(links=0, leads=0, opportunities=0),
            review=review(with_post=False),
            projected_at=AS_OF,
        )
        snapshot = {row["key"]: row for row in payload["domains"]}["RESULTS_SNAPSHOT"]
        self.assertEqual(snapshot["status"], "NOT_OBSERVED")
        self.assertNotIn("FAILED", json.dumps(payload))
        self.assertNotIn("BAD_PERFORMANCE", json.dumps(payload))
        self.assertTrue(payload["contracts"]["no_business_health_score"])

    def test_missing_invalid_and_future_timestamps_never_become_staleness_claims(self):
        no_time_results = results()
        no_time_results["latest_snapshot"]["created_at"] = None
        missing = compose_evidence_observability(
            company={"id": "c1"}, results=no_time_results, outcomes=outcomes(), review=review(), projected_at=AS_OF,
        )["domains"][0]
        self.assertEqual(missing["status"], "PARTIAL")
        self.assertEqual(missing["freshness"]["classification"], "NO_OBSERVATION_TIMESTAMP")

        bad_results = results()
        bad_results["latest_snapshot"]["created_at"] = "not-a-date"
        invalid = compose_evidence_observability(
            company={"id": "c1"}, results=bad_results, outcomes=outcomes(), review=review(), projected_at=AS_OF,
        )["domains"][0]
        self.assertEqual(invalid["freshness"]["classification"], "INVALID_TIMESTAMP")

        future_results = results()
        future_results["latest_snapshot"]["created_at"] = "2026-08-25T20:00:00+00:00"
        future = compose_evidence_observability(
            company={"id": "c1"}, results=future_results, outcomes=outcomes(), review=review(), projected_at=AS_OF,
        )["domains"][0]
        self.assertEqual(future["freshness"]["classification"], "FUTURE_OBSERVATION")
        self.assertIsNone(future["freshness"]["age_seconds"])
        self.assertIsNone(future["freshness"]["fresh"])
        self.assertIsNone(future["freshness"]["stale"])

    def test_post_decision_evidence_is_temporal_not_causal(self):
        payload = compose_evidence_observability(
            company={"id": "c1"}, results=results(), outcomes=outcomes(), review=review(with_post=True), projected_at=AS_OF,
        )
        decision = {row["key"]: row for row in payload["domains"]}["DECISION_EVIDENCE"]
        self.assertEqual(decision["status"], "OBSERVED")
        self.assertEqual(decision["coverage"]["with_post_decision_evidence"], 1)
        self.assertTrue(any("no demuestra" in text.lower() for text in decision["caveats"]))
        self.assertTrue(payload["contracts"]["no_causal_inference"])

    def test_empty_surfaces_are_unknown_or_not_observed_without_numeric_invention(self):
        payload = compose_evidence_observability(
            company={"id": "c1"},
            results={"latest_snapshot": None, "summary": {"campaigns": 0}, "campaigns": []},
            outcomes={"summary": {}, "campaigns": []},
            review={"summary": {}, "campaigns": []},
            projected_at=AS_OF,
        )
        self.assertEqual([row["status"] for row in payload["domains"]], ["UNKNOWN", "UNKNOWN", "UNKNOWN", "UNKNOWN"])
        self.assertEqual(payload["summary"]["unknown"], 4)
        self.assertTrue(payload["safety"]["read_only_projection"])
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["business_mutation_performed"])


class EvidenceRuntimeIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company_a = self.runtime.create_company({"name": "Empresa A"})
        self.company_b = self.runtime.create_company({"name": "Empresa B"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_terminal_runtime_preserves_today_and_adds_company_scoped_evidence(self):
        today = self.runtime.today_execution(self.company_a["id"])
        evidence = self.runtime.evidence_observability(self.company_a["id"])
        self.assertEqual(today["schema"], "binario.marketing.today-execution.v1")
        self.assertEqual(evidence["schema"], "binario.marketing.evidence-observability.v1")
        self.assertEqual(evidence["company"]["id"], self.company_a["id"])
        self.assertNotEqual(evidence["company"]["id"], self.company_b["id"])
        self.assertTrue(evidence["contracts"]["action_center_priority_unmodified"])
        self.assertTrue(evidence["contracts"]["today_selection_unmodified"])

    def test_http_bootstrap_chain_reaches_evidence_and_endpoints_coexist(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            host = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(host + "/executive-cockpit.js", timeout=5) as response:
                executive = response.read().decode("utf-8")
            self.assertIn("today-execution.js", executive)
            with urlopen(host + "/today-execution.js", timeout=5) as response:
                today_bootstrap = response.read().decode("utf-8")
            self.assertIn("evidence-observability.js", today_bootstrap)
            self.assertIn("data-post-w99-evidence-observability", today_bootstrap)
            with urlopen(host + f"/api/companies/{self.company_a['id']}/today-execution", timeout=5) as response:
                today = json.loads(response.read().decode("utf-8"))
            with urlopen(host + f"/api/companies/{self.company_a['id']}/evidence-observability", timeout=5) as response:
                evidence = json.loads(response.read().decode("utf-8"))
            self.assertEqual(today["schema"], "binario.marketing.today-execution.v1")
            self.assertEqual(evidence["schema"], "binario.marketing.evidence-observability.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_evidence_layer_is_get_only_and_has_no_provider_or_mutation_transport(self):
        service = (ROOT / "src/binario_marketing/service_post_w99_evidence_observability_app.py").read_text(encoding="utf-8")
        ui = (ROOT / "web/evidence-observability.js").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_today_execution_app as base", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertNotIn("MetaObservability", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("method:'POST'", ui)
        self.assertNotIn('method:"POST"', ui)
        self.assertNotIn("sendBeacon", ui)
        self.assertIn("Actualizar lectura local", ui)
        self.assertIn("Sin umbral de obsolescencia configurado", ui)


if __name__ == "__main__":
    unittest.main()
