import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_portfolio_cadence_app import (
    AppRuntime,
    create_server,
    normalize_action_timing,
    portfolio_cadence_projection,
)

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 8, 25, 16, 0, tzinfo=timezone.utc)


def item(*, source="COMMERCIAL", kind="lead_new", due_at=None, item_id="x"):
    return {
        "id": item_id,
        "portfolio_id": f"co:{item_id}",
        "company": {"id": "co", "name": "Company"},
        "source": source,
        "kind": kind,
        "title": item_id,
        "due_at": due_at,
        "action": {"view": "commercial-desk"},
    }


class FakeRuntime:
    def __init__(self, payload):
        self.payload = payload

    def portfolio_control_tower(self):
        return self.payload


class PostW99PortfolioCadencePureTests(unittest.TestCase):
    def test_future_received_at_is_anomaly_not_zero_age(self):
        timing = normalize_action_timing(
            item(due_at="2026-08-25T18:00:00+00:00"),
            now=NOW,
        )
        self.assertEqual(timing["kind"], "RECEIVED_AT")
        self.assertEqual(timing["state"], "FUTURE_RECEIVED_AT")
        self.assertIsNone(timing["age_hours"])
        self.assertTrue(timing["temporal_anomaly"])
        self.assertFalse(timing["is_deadline"])

    def test_invalid_and_missing_received_at_are_explicit(self):
        invalid = normalize_action_timing(item(due_at="not-a-date"), now=NOW)
        missing = normalize_action_timing(item(due_at=None), now=NOW)
        self.assertEqual(invalid["state"], "INVALID_RECEIVED_AT")
        self.assertEqual(invalid["timestamp_quality"], "INVALID_TIMESTAMP")
        self.assertIsNone(invalid["age_hours"])
        self.assertEqual(missing["state"], "MISSING_RECEIVED_AT")
        self.assertEqual(missing["timestamp_quality"], "MISSING_EXPECTED_TIMESTAMP")
        self.assertIsNone(missing["age_hours"])

    def test_valid_received_at_age_is_observational(self):
        timing = normalize_action_timing(
            item(due_at="2026-08-25T14:00:00+00:00"),
            now=NOW,
        )
        self.assertEqual(timing["state"], "RECEIVED_LE_24H")
        self.assertEqual(timing["age_hours"], 2.0)
        self.assertFalse(timing["is_deadline"])
        self.assertFalse(timing["temporal_anomaly"])

    def test_source_declared_deadline_is_preserved_but_timestamp_is_audited(self):
        timing = normalize_action_timing(
            item(
                source="OPERATIONS",
                kind="crm_overdue",
                due_at="2026-08-26T10:00:00+00:00",
            ),
            now=NOW,
        )
        self.assertEqual(timing["kind"], "DEADLINE")
        self.assertEqual(timing["state"], "OVERDUE")
        self.assertTrue(timing["is_deadline"])
        self.assertEqual(timing["timestamp_quality"], "FUTURE_TIMESTAMP")
        self.assertTrue(timing["temporal_anomaly"])
        self.assertFalse(timing["inferred"])

    def test_unscheduled_handoff_never_gets_invented_deadline(self):
        timing = normalize_action_timing(
            item(source="COMMERCIAL", kind="needs_opportunity", due_at=None),
            now=NOW,
        )
        self.assertEqual(timing["kind"], "UNSCHEDULED")
        self.assertEqual(timing["state"], "UNSCHEDULED")
        self.assertFalse(timing["is_deadline"])
        self.assertIsNone(timing["at"])

    def test_projection_preserves_parent_order_and_declares_truncation(self):
        queue = [
            item(source="SETUP", kind="setup_gap", item_id="first"),
            item(due_at="2026-08-25T18:00:00+00:00", item_id="second"),
        ]
        runtime = FakeRuntime(
            {
                "schema": "binario.marketing.portfolio-control-tower.v1",
                "summary": {"queue_total": 5},
                "queue": queue,
            }
        )
        payload = portfolio_cadence_projection(
            runtime,
            generated_at="2026-08-25T16:00:00+00:00",
        )
        self.assertEqual(payload["schema"], "binario.marketing.portfolio-cadence.v2")
        self.assertEqual([row["id"] for row in payload["queue"]], ["first", "second"])
        self.assertEqual(payload["next_action"]["id"], "first")
        self.assertTrue(payload["summary"]["parent_queue_truncated"])
        self.assertEqual(payload["scope"]["completeness"], "PARTIAL_PARENT_QUEUE")
        self.assertEqual(payload["summary"]["temporal_anomalies"], 1)
        self.assertEqual(payload["summary"]["received_age"]["future"], 1)
        self.assertTrue(payload["contracts"]["exact_parent_queue_order_preserved"])
        self.assertTrue(payload["contracts"]["future_received_at_never_zero_age"])

    def test_first_deadline_means_priority_order_not_chronology(self):
        queue = [
            item(
                source="OPERATIONS",
                kind="publication_today",
                due_at="2026-08-25T12:00:00+00:00",
                item_id="priority-first",
            ),
            item(
                source="OPERATIONS",
                kind="crm_overdue",
                due_at="2026-08-24T08:00:00+00:00",
                item_id="older-date-second",
            ),
        ]
        runtime = FakeRuntime(
            {
                "schema": "binario.marketing.portfolio-control-tower.v1",
                "summary": {"queue_total": 2},
                "queue": queue,
            }
        )
        payload = portfolio_cadence_projection(
            runtime,
            generated_at="2026-08-25T16:00:00+00:00",
        )
        self.assertEqual(
            payload["first_explicit_deadline_in_priority_order"]["id"],
            "priority-first",
        )
        self.assertEqual(
            payload["contracts"]["deadline_selection_rule"],
            "FIRST_DEADLINE_IN_CANONICAL_PRIORITY_ORDER",
        )

    def test_invalid_generated_at_is_rejected(self):
        runtime = FakeRuntime(
            {
                "schema": "binario.marketing.portfolio-control-tower.v1",
                "summary": {"queue_total": 0},
                "queue": [],
            }
        )
        with self.assertRaisesRegex(ValueError, "generated_at"):
            portfolio_cadence_projection(runtime, generated_at="invalid")


class PostW99PortfolioCadenceIntegrationTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_runtime_preserves_current_chain_and_adds_cadence(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Cadence Integrated"})
                company_id = company["id"]
                self.assertEqual(
                    runtime.today_execution(company_id)["schema"],
                    "binario.marketing.today-execution.v1",
                )
                self.assertEqual(
                    runtime.evidence_observability(company_id)["schema"],
                    "binario.marketing.evidence-observability.v1",
                )
                self.assertEqual(
                    runtime.portfolio_cadence()["schema"],
                    "binario.marketing.portfolio-cadence.v2",
                )
            finally:
                self._shutdown_runtime(runtime)

    def test_browser_bootstrap_chain_is_cumulative(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Cadence HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                today = urlopen(root + "/today-execution.js", timeout=5).read().decode("utf-8")
                execution = urlopen(root + "/execution-return.js", timeout=5).read().decode("utf-8")
                contextual = urlopen(root + "/contextual-deep-linking.js", timeout=5).read().decode("utf-8")
                evidence = urlopen(root + "/evidence-observability.js", timeout=5).read().decode("utf-8")
                cadence = urlopen(root + "/portfolio-cadence.js", timeout=5).read().decode("utf-8")
                self.assertIn("/execution-return.js", today)
                self.assertIn("/contextual-deep-linking.js", execution)
                self.assertIn("/evidence-observability.js", contextual)
                self.assertIn("/portfolio-cadence.js", evidence)
                self.assertIn("postW99CadenceState", cadence)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_global_endpoint_is_read_only_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Cadence API"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                payload = json.loads(
                    urlopen(root + "/api/portfolio-cadence", timeout=5).read()
                )
                self.assertEqual(payload["schema"], "binario.marketing.portfolio-cadence.v2")
                self.assertTrue(payload["safety"]["read_only_projection"])
                self.assertFalse(payload["safety"]["provider_read_performed"])
                self.assertFalse(payload["safety"]["business_mutation_performed"])
                self.assertTrue(payload["contracts"]["parent_queue_scope_declared"])
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_docs_preserve_frozen_release_boundary(self):
        docs = (ROOT / "docs" / "POST_W99_PORTFOLIO_CADENCE.md").read_text(encoding="utf-8")
        entrypoint = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("FUTURE_RECEIVED_AT", docs)
        self.assertIn("PARTIAL_PARENT_QUEUE", docs)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn(
            "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence",
            entrypoint,
        )
        self.assertIn("No debe interpretarse como W100", entrypoint)


if __name__ == "__main__":
    unittest.main()
