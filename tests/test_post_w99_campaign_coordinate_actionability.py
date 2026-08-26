import copy
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing import service_post_w99_campaign_media_candidate_selection_handoff_app as parent
from binario_marketing.service_post_w99_campaign_coordinate_actionability_app import (
    AppRuntime,
    _exact_recovery_is_actionable,
    create_server,
    preserve_coordinate_actionability,
)


ROOT = Path(__file__).resolve().parents[1]


def _row(
    action_id: str,
    *,
    kind: str = "coordinate",
    source: str = "CAMPAIGN",
    urgency: str = "LOW",
) -> dict:
    return {
        "id": action_id,
        "rank": 74,
        "urgency": urgency,
        "source": source,
        "kind": kind,
        "title": f"{kind} · Campaign",
        "detail": f"detail {action_id}",
        "action": {
            "label": "Coordinar distribución",
            "view": "content",
            "tab": None,
            "entity_id": None,
            "campaign_id": "campaign-1",
            "media_id": None,
        },
        "reason": {
            "code": f"{source}_{kind}".upper(),
            "explanation": "canonical reason",
        },
        "due_at": None,
        "blocking": False,
        "requires_human_action": True,
        "read_only_recommendation": True,
    }


def _payload(queue: list[dict], observations: list[dict] | None = None) -> dict:
    return {
        "schema": "binario.marketing.action-center.v1",
        "company": {"id": "company-1", "name": "Company"},
        "next_action": queue[0] if queue else None,
        "summary": {
            "queue_total": len(queue),
            "blocking": sum(1 for row in queue if row.get("blocking")),
            "critical": sum(1 for row in queue if row["urgency"] == "CRITICAL"),
            "high": sum(1 for row in queue if row["urgency"] == "HIGH"),
            "medium": sum(1 for row in queue if row["urgency"] == "MEDIUM"),
            "low": sum(1 for row in queue if row["urgency"] == "LOW"),
            "by_source": {
                "OPERATIONS": 0,
                "COMMERCIAL": 0,
                "CAMPAIGN": sum(
                    1 for row in queue if row.get("source") == "CAMPAIGN"
                ),
                "SETUP": 0,
            },
            "campaign_actions": sum(
                1 for row in queue if row.get("source") == "CAMPAIGN"
            ),
            "observations_total": len(observations or []),
            "campaign_observations": sum(
                1
                for row in (observations or [])
                if row.get("source") == "CAMPAIGN"
                and row.get("kind") == "planned_only"
            ),
        },
        "focus": {
            "now": [
                row
                for row in queue
                if row["urgency"] in {"CRITICAL", "HIGH"}
            ][:8],
            "next": [
                row for row in queue if row["urgency"] == "MEDIUM"
            ][:8],
            "later": [
                row for row in queue if row["urgency"] == "LOW"
            ][:8],
        },
        "queue": list(queue),
        "observations": list(observations or []),
        "contracts": {
            "planned_only_is_observational": True,
            "planned_only_excluded_from_today": True,
        },
        "safety": {
            "read_only_projection": True,
            "business_mutation_performed": False,
        },
    }


def _coordinate(
    action_id: str,
    *,
    coordinate_state: str,
    recovery_state: str,
) -> dict:
    row = _row(action_id)
    row["coordinate_state"] = {
        "schema": "binario.marketing.campaign-coordinate-state.v1",
        "state": coordinate_state,
    }
    row["coordinate_recovery"] = {
        "schema": "binario.marketing.campaign-coordinate-recovery-guidance.v1",
        "source_coordinate_state": coordinate_state,
        "state": recovery_state,
        "intent": "NONE",
        "owner_view": None,
        "target_kind": None,
        "target_id": None,
        "recovery_controls": [],
        "candidates": {
            "publishing_publications": [],
            "cancelled_publications": [],
            "cancelled_paid": [],
            "source_media": [],
        },
    }
    return row


def _exact_recovery(action_id: str = "coordinate-exact") -> dict:
    row = _coordinate(
        action_id,
        coordinate_state="ONLY_CANCELLED_DISTRIBUTION_REMAINS",
        recovery_state="EXACT_RECOVERY_OWNER",
    )
    row["action"].update(
        {
            "label": "Preparar nueva distribución desde creativo exacto",
            "view": "content",
            "media_id": "media-1",
        }
    )
    recovery = row["coordinate_recovery"]
    recovery.update(
        {
            "source_coordinate_state": "ONLY_CANCELLED_DISTRIBUTION_REMAINS",
            "intent": "CREATE_NEW_DISTRIBUTION_FROM_CANCELLED_LINEAGE",
            "owner_view": "content",
            "target_kind": "MEDIA",
            "target_id": "media-1",
            "recovery_controls": ["PREPARE_INSTAGRAM"],
            "candidates": {
                "publishing_publications": [],
                "cancelled_publications": [{"id": "pub-1"}],
                "cancelled_paid": [],
                "source_media": [{"id": "media-1", "stage": "READY"}],
            },
        }
    )
    return row


class CoordinateActionabilityProjectionTests(unittest.TestCase):
    def test_publication_in_flight_exact_existing_owner_is_observation(self):
        before = _row("before", kind="review_results", urgency="MEDIUM")
        coordinate = _coordinate(
            "coordinate",
            coordinate_state="PUBLICATION_IN_FLIGHT",
            recovery_state="EXACT_EXISTING_OWNER",
        )
        coordinate["coordinate_recovery"].update(
            {
                "intent": "OBSERVE_PUBLICATION_IN_FLIGHT",
                "owner_view": "calendar",
                "target_kind": "PUBLICATION",
                "target_id": "pub-1",
            }
        )
        coordinate["action"].update(
            {
                "view": "calendar",
                "entity_id": "pub-1",
                "label": "Revisar publicación en curso",
            }
        )
        after = _row("after", kind="optional_ai", urgency="LOW")
        result = preserve_coordinate_actionability(
            _payload([before, coordinate, after])
        )

        self.assertEqual([row["id"] for row in result["queue"]], ["before", "after"])
        observation = next(
            row for row in result["observations"] if row["id"] == "coordinate"
        )
        self.assertFalse(observation["requires_human_action"])
        self.assertFalse(observation["blocking"])
        self.assertEqual(
            observation["actionability"]["state"],
            "NON_ACTIONABLE_COORDINATE",
        )
        self.assertFalse(observation["actionability"]["today_eligible"])
        self.assertEqual(
            observation["actionability"]["coordinate_state"],
            "PUBLICATION_IN_FLIGHT",
        )
        self.assertEqual(
            observation["actionability"]["recovery_state"],
            "EXACT_EXISTING_OWNER",
        )
        self.assertEqual(
            observation["coordinate_recovery"]["target_id"],
            "pub-1",
        )

    def test_exact_cancelled_lineage_recovery_stays_actionable(self):
        exact = _exact_recovery()
        self.assertTrue(_exact_recovery_is_actionable(exact))
        result = preserve_coordinate_actionability(_payload([exact]))

        self.assertEqual([row["id"] for row in result["queue"]], ["coordinate-exact"])
        self.assertEqual(result["observations"], [])
        current = result["queue"][0]
        self.assertTrue(current["requires_human_action"])
        self.assertEqual(
            current["coordinate_actionability"]["state"],
            "ACTIONABLE_EXACT_RECOVERY",
        )
        self.assertTrue(current["coordinate_actionability"]["today_eligible"])
        self.assertEqual(result["summary"]["coordinate_exact_recovery_actions"], 1)

    def test_malformed_exact_recovery_fails_closed(self):
        variants = []

        mismatch = _exact_recovery("mismatch")
        mismatch["action"]["media_id"] = "media-other"
        variants.append(mismatch)

        missing_source = _exact_recovery("missing-source")
        missing_source["coordinate_recovery"]["candidates"]["source_media"] = []
        variants.append(missing_source)

        duplicate_control = _exact_recovery("duplicate-control")
        duplicate_control["coordinate_recovery"]["recovery_controls"] = [
            "PREPARE_INSTAGRAM",
            "PREPARE_INSTAGRAM",
        ]
        variants.append(duplicate_control)

        unknown_control = _exact_recovery("unknown-control")
        unknown_control["coordinate_recovery"]["recovery_controls"] = [
            "RETRY_REMOTE_PUBLICATION"
        ]
        variants.append(unknown_control)

        for row in variants:
            with self.subTest(row=row["id"]):
                self.assertFalse(_exact_recovery_is_actionable(row))
                result = preserve_coordinate_actionability(_payload([row]))
                self.assertEqual(result["queue"], [])
                self.assertEqual(
                    result["observations"][0]["actionability"]["state"],
                    "NON_ACTIONABLE_COORDINATE",
                )

    def test_all_nonrecoverable_and_future_coordinate_states_fail_closed(self):
        cases = [
            ("ONLY_CANCELLED_DISTRIBUTION_REMAINS", "AMBIGUOUS_RECOVERY_OWNER"),
            ("ONLY_CANCELLED_DISTRIBUTION_REMAINS", "RECOVERY_OWNER_GAP"),
            ("ONLY_CANCELLED_DISTRIBUTION_REMAINS", "RECOVERY_INVARIANT_GAP"),
            ("PUBLICATION_IN_FLIGHT", "AMBIGUOUS_EXISTING_OWNER"),
            ("COORDINATE_INVARIANT_DRIFT", "DIAGNOSTIC_ONLY"),
            ("UNCLASSIFIED_COORDINATION_STATE", "DIAGNOSTIC_ONLY"),
            ("FUTURE_COORDINATE_STATE", "FUTURE_RECOVERY_STATE"),
        ]
        rows = [
            _coordinate(
                f"coordinate-{index}",
                coordinate_state=coordinate_state,
                recovery_state=recovery_state,
            )
            for index, (coordinate_state, recovery_state) in enumerate(cases)
        ]
        result = preserve_coordinate_actionability(_payload(rows))
        self.assertEqual(result["queue"], [])
        self.assertEqual(len(result["observations"]), len(cases))
        self.assertTrue(result["contracts"]["unknown_coordinate_states_fail_closed"])
        self.assertTrue(
            result["contracts"]["coordinate_nonrecoverable_states_are_observational"]
        )

    def test_non_coordinate_rows_are_always_preserved_in_order(self):
        rows = [
            _row("one", kind="calendar", urgency="HIGH"),
            _row("two", kind="review_paid", urgency="MEDIUM"),
            _row("three", kind="setup", source="SETUP", urgency="LOW"),
        ]
        result = preserve_coordinate_actionability(_payload(rows))
        self.assertEqual(
            [row["id"] for row in result["queue"]],
            ["one", "two", "three"],
        )
        self.assertEqual(result["observations"], [])

    def test_projection_is_idempotent_and_preserves_planned_observation(self):
        planned = _row("planned", kind="planned_only")
        planned["requires_human_action"] = False
        planned["actionability"] = {
            "state": "NON_ACTIONABLE",
            "today_eligible": False,
        }
        source = _payload(
            [
                _coordinate(
                    "coordinate",
                    coordinate_state="COORDINATE_INVARIANT_DRIFT",
                    recovery_state="DIAGNOSTIC_ONLY",
                )
            ],
            observations=[planned],
        )
        once = preserve_coordinate_actionability(source)
        twice = preserve_coordinate_actionability(once)

        self.assertEqual(len(twice["observations"]), 2)
        self.assertEqual(
            [row["id"] for row in twice["observations"]],
            ["planned", "coordinate"],
        )
        self.assertEqual(twice["summary"]["campaign_observations"], 1)
        self.assertEqual(twice["summary"]["coordinate_observations"], 1)

    def test_next_focus_summary_and_source_input_are_recomputed_without_mutation(self):
        high = _row("high", kind="capture_results", urgency="HIGH")
        coordinate = _coordinate(
            "coordinate",
            coordinate_state="PUBLICATION_IN_FLIGHT",
            recovery_state="EXACT_EXISTING_OWNER",
        )
        low = _row("low", kind="optional_ai", urgency="LOW")
        source = _payload([coordinate, high, low])
        original = copy.deepcopy(source)

        result = preserve_coordinate_actionability(source)

        self.assertEqual(source, original)
        self.assertEqual(result["next_action"]["id"], "high")
        self.assertEqual([row["id"] for row in result["focus"]["now"]], ["high"])
        self.assertEqual(result["focus"]["next"], [])
        self.assertEqual([row["id"] for row in result["focus"]["later"]], ["low"])
        self.assertEqual(result["summary"]["queue_total"], 2)
        self.assertEqual(result["summary"]["campaign_actions"], 2)
        self.assertEqual(result["summary"]["coordinate_observations"], 1)
        self.assertTrue(
            result["contracts"]["coordinate_action_order_preserved_after_filter"]
        )


class CoordinateActionabilityIntegrationTests(unittest.TestCase):
    def _shutdown(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_terminal_inherits_current_media_selection_parent(self):
        self.assertTrue(issubclass(AppRuntime, parent.AppRuntime))

    def test_http_bootstrap_appends_coordinate_actionability_after_media_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            runtime.create_company({"name": "Coordinate Actionability HTTP"})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent_js = urlopen(
                    root + "/campaign-media-candidate-selection-handoff.js",
                    timeout=5,
                ).read().decode("utf-8")
                adapter = urlopen(
                    root + "/campaign-coordinate-actionability.js",
                    timeout=5,
                ).read().decode("utf-8")
                self.assertIn(
                    "/campaign-coordinate-actionability.js",
                    parent_js,
                )
                self.assertIn(
                    "data-post-w99-campaign-coordinate-actionability",
                    parent_js,
                )
                self.assertIn("COORDINACIÓN · OBSERVACIONES", adapter)
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown(runtime)

    def test_service_browser_and_docs_preserve_read_only_frozen_boundary(self):
        service = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_campaign_coordinate_actionability_app.py"
        ).read_text(encoding="utf-8")
        browser = (
            ROOT / "web" / "campaign-coordinate-actionability.js"
        ).read_text(encoding="utf-8")
        doc = (
            ROOT
            / "docs"
            / "POST_W99_CAMPAIGN_COORDINATE_ACTIONABILITY.md"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "service_post_w99_campaign_media_candidate_selection_handoff_app",
            service,
        )
        for forbidden in (
            "def do_POST",
            "def do_PATCH",
            "def do_PUT",
            "def do_DELETE",
        ):
            self.assertNotIn(forbidden, service)
        for forbidden in (
            "opsApi(",
            "fetch(",
            ".click(",
            "dispatchEvent(",
            "setInterval(",
            "sendBeacon(",
            "method:'POST'",
            "method:'PATCH'",
            "method:'PUT'",
            "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, browser)

        self.assertIn(
            "main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53",
            doc,
        )
        self.assertIn(
            "53d1cf04a67da4308b37ac03c0be4546a04f36eb",
            doc,
        )
        self.assertIn("No constituye W100", doc)
        self.assertIn("Physical UAT", doc)

    def test_wave64_and_today_source_contracts_explain_the_actionability_fix(self):
        wave64 = (
            ROOT / "src" / "binario_marketing" / "service_wave64_app.py"
        ).read_text(encoding="utf-8")
        today = (
            ROOT
            / "src"
            / "binario_marketing"
            / "service_post_w99_today_execution_app.py"
        ).read_text(encoding="utf-8")

        coordinate_block = wave64.split(
            'next_action = {"code": "COORDINATE"',
            1,
        )[1].split("cards.append", 1)[0]
        self.assertIn("requires_action = False", coordinate_block)
        self.assertIn("action_center = self.action_center(company.id)", today)
        self.assertIn("canonical_queue = list(action_center.get(\"queue\") or [])", today)


if __name__ == "__main__":
    unittest.main()
