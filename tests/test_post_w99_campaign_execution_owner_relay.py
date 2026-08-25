import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen

from binario_marketing.service_post_w99_campaign_execution_owner_relay_app import (
    AppRuntime,
    _owner_resolution,
    _rewrite_action_from_resolution,
    create_server,
)

ROOT = Path(__file__).resolve().parents[1]


class PostW99CampaignExecutionOwnerRelayTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_fix_publication_routes_only_one_failed_publication(self):
        resolution = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "FIX_PUBLICATION", "view": "calendar"},
            linked_creatives=[],
            publications=[{"id": "pub_failed", "status": "FAILED", "channel": "instagram"}],
            linked_paid=[],
        )
        self.assertEqual(resolution["state"], "EXACT_TARGET")
        self.assertEqual(resolution["target_kind"], "PUBLICATION")
        self.assertEqual(resolution["target_id"], "pub_failed")
        self.assertEqual(resolution["candidate_count"], 1)

    def test_fix_publication_fails_closed_when_more_than_one_failed(self):
        resolution = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "FIX_PUBLICATION", "view": "calendar"},
            linked_creatives=[],
            publications=[
                {"id": "pub_a", "status": "FAILED", "channel": "instagram"},
                {"id": "pub_b", "status": "FAILED", "channel": "facebook_page"},
            ],
            linked_paid=[],
        )
        self.assertEqual(resolution["state"], "AMBIGUOUS_TARGET")
        self.assertIsNone(resolution["target_id"])
        self.assertEqual(resolution["candidate_count"], 2)
        self.assertIn("No se elige", resolution["reason"])

    def test_schedule_and_paid_resolution_require_unique_existing_owner(self):
        draft = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "SCHEDULE_OR_PUBLISH", "view": "calendar"},
            linked_creatives=[],
            publications=[{"id": "draft_pub", "status": "DRAFT"}],
            linked_paid=[],
        )
        self.assertEqual((draft["state"], draft["target_kind"], draft["target_id"]), ("EXACT_TARGET", "PUBLICATION", "draft_pub"))

        paid = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "REVIEW_PAID", "view": "pauta"},
            linked_creatives=[],
            publications=[],
            linked_paid=[{"id": "paid_draft", "status": "DRAFT", "campaign_name": "Meta draft"}],
        )
        self.assertEqual((paid["state"], paid["target_kind"], paid["target_id"]), ("EXACT_TARGET", "PAID_DRAFT", "paid_draft"))

        ambiguous_paid = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "REVIEW_PAID", "view": "pauta"},
            linked_creatives=[],
            publications=[],
            linked_paid=[{"id": "p1", "status": "DRAFT"}, {"id": "p2", "status": "DRAFT"}],
        )
        self.assertEqual(ambiguous_paid["state"], "AMBIGUOUS_TARGET")
        self.assertIsNone(ambiguous_paid["target_id"])

    def test_media_resolution_requires_w64_media_id_to_exist_once(self):
        creatives = [
            {"media": {"id": "media_exact", "original_name": "Exact.png"}, "creative": {"title": "Exact"}, "effective_stage": "DRAFT"},
            {"media": {"id": "media_other", "original_name": "Other.png"}, "creative": {"title": "Other"}, "effective_stage": "READY"},
        ]
        resolution = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "FINISH_CREATIVE", "view": "content", "media_id": "media_exact"},
            linked_creatives=creatives,
            publications=[],
            linked_paid=[],
        )
        self.assertEqual((resolution["state"], resolution["target_kind"], resolution["target_id"]), ("EXACT_TARGET", "MEDIA", "media_exact"))

        missing = _owner_resolution(
            campaign_id="campaign_exact",
            next_action={"code": "FINISH_CREATIVE", "view": "content", "media_id": "media_missing"},
            linked_creatives=creatives,
            publications=[],
            linked_paid=[],
        )
        self.assertEqual(missing["state"], "NO_TARGET")
        self.assertIsNone(missing["target_id"])

    def test_create_or_coordinate_work_remains_owner_only(self):
        for code in ("CREATE_CREATIVE", "COORDINATE"):
            with self.subTest(code=code):
                resolution = _owner_resolution(
                    campaign_id="campaign_exact",
                    next_action={"code": code, "view": "content"},
                    linked_creatives=[],
                    publications=[],
                    linked_paid=[],
                )
                self.assertEqual(resolution["state"], "OWNER_ONLY")
                self.assertIsNone(resolution["target_id"])

    def test_exact_rewrite_preserves_priority_identity_and_due_semantics(self):
        row = {
            "id": "action-stable",
            "rank": 5,
            "urgency": "CRITICAL",
            "due_at": "2026-08-25T10:00:00+00:00",
            "blocking": True,
            "kind": "fix_execution",
            "action": {"label": "Resolver publicación fallida", "view": "execution", "campaign_id": "campaign_exact", "entity_id": None},
        }
        resolution = {
            "state": "EXACT_TARGET",
            "source_code": "FIX_PUBLICATION",
            "owner_view": "calendar",
            "target_kind": "PUBLICATION",
            "target_id": "pub_exact",
            "candidate_count": 1,
            "candidates": [{"id": "pub_exact"}],
            "reason": "exact",
        }
        routed = _rewrite_action_from_resolution(row, resolution)
        for key in ("id", "rank", "urgency", "due_at", "blocking", "kind"):
            self.assertEqual(routed[key], row[key])
        self.assertEqual(routed["action"]["view"], "calendar")
        self.assertEqual(routed["action"]["entity_id"], "pub_exact")
        self.assertEqual(routed["action"]["campaign_id"], "campaign_exact")
        self.assertEqual(routed["owner_resolution"]["state"], "EXACT_TARGET")
        self.assertEqual(row["action"]["view"], "execution")

    def test_runtime_context_is_local_read_only_and_campaign_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Execution Relay"})
                campaign = runtime.campaigns.create(company["id"], {
                    "name": "Sin canales",
                    "objective": "LEADS",
                    "status": "IN_PROGRESS",
                    "channels": [],
                })
                context = runtime.campaign_execution_owner_context(company["id"], campaign.id)
                self.assertEqual(context["schema"], "binario.marketing.campaign-execution-owner-context.v1")
                self.assertEqual(context["campaign"]["id"], campaign.id)
                self.assertEqual(context["execution"]["next_action"]["code"], "DEFINE_CHANNELS")
                self.assertEqual(context["resolution"]["state"], "EXACT_TARGET")
                self.assertEqual(context["resolution"]["target_kind"], "CAMPAIGN")
                self.assertEqual(context["resolution"]["target_id"], campaign.id)
                self.assertTrue(context["contracts"]["w64_remains_next_action_authority"])
                self.assertTrue(context["contracts"]["ambiguous_target_fails_closed"])
                self.assertEqual(context["safety"], {
                    "provider_read_performed": False,
                    "provider_mutation_performed": False,
                    "business_mutation_performed": False,
                    "ai_generation_performed": False,
                    "automatic_execution": False,
                    "background_polling": False,
                    "cloud_required": False,
                })
                action = next(row for row in runtime.action_center(company["id"])["queue"] if row.get("kind") == "define_channels")
                self.assertEqual(action["owner_resolution"]["state"], "EXACT_TARGET")
                self.assertEqual(action["action"]["view"], "campaigns")
                self.assertEqual(action["action"]["campaign_id"], campaign.id)
            finally:
                self._shutdown_runtime(runtime)

    def test_http_context_is_get_only_and_adapter_bootstraps_after_results_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company = runtime.create_company({"name": "Execution HTTP"})
            campaign = runtime.campaigns.create(company["id"], {"name": "Exact", "objective": "LEADS", "status": "IN_PROGRESS", "channels": []})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True);thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                payload = json.loads(urlopen(root + f"/api/companies/{company['id']}/campaigns/{campaign.id}/execution-owner-context", timeout=5).read().decode("utf-8"))
                self.assertEqual(payload["campaign"]["id"], campaign.id)
                previous = urlopen(root + "/campaign-results-owner-handoff.js", timeout=5).read().decode("utf-8")
                current = urlopen(root + "/campaign-execution-owner-relay.js", timeout=5).read().decode("utf-8")
                self.assertIn("/campaign-execution-owner-relay.js", previous)
                self.assertIn("PAID_DRAFT", current)
                self.assertIn("deepMediaId", current)
                with self.assertRaises(HTTPError) as raised:
                    urlopen(root + f"/api/companies/{company['id']}/campaigns/not-a-campaign/execution-owner-context", timeout=5)
                self.assertIn(raised.exception.code, {400, 404})
            finally:
                server.shutdown();thread.join(timeout=5);server.server_close();self._shutdown_runtime(runtime)

    def test_browser_adapter_repairs_wave49_media_and_wave48_paid_exactness_without_mutation(self):
        source = (ROOT / "web" / "campaign-execution-owner-relay.js").read_text(encoding="utf-8")
        for required in (
            ".w49-list .w49-item",
            "node.dataset.deepMediaId",
            "wave49CreativeState.selectedId",
            "wave49CreativeState.tab='pipeline'",
            ".wave48-plans .wave48-plan",
            "node.dataset.deepPaidDraftId",
            "PAID_DRAFT",
            "W42_EXACT_PUBLICATION_OWNER",
            "W49_FINISH_CREATIVE",
            "W49_PREPARE_DISTRIBUTION",
            "W48_REVIEW_PAID_DRAFT",
            "W35_DEFINE_CHANNELS",
        ):
            self.assertIn(required, source)
        self.assertIn("nodes.length!==rows.length", source)
        for forbidden in (
            "opsApi(",
            ".click(",
            "dispatchEvent(",
            "setInterval(",
            "sendBeacon(",
            "method:'POST'",
            "method:'PATCH'",
            "method:'PUT'",
            "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, source)

    def test_service_does_not_add_business_write_route(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_execution_owner_relay_app.py").read_text(encoding="utf-8")
        self.assertIn("def campaign_execution_owner_context", source)
        self.assertIn("def action_center", source)
        self.assertIn("execution-owner-context", source)
        self.assertNotIn("def do_POST", source)
        self.assertNotIn("def do_PATCH", source)
        self.assertNotIn("def do_PUT", source)
        self.assertNotIn("def do_DELETE", source)
        self.assertIn("campaign_execution_workspace", source)
        self.assertIn("company_creatives_payload", source)
        self.assertIn("company_paid_media", source)

    def test_docs_preserve_frozen_w99_boundary_and_fail_closed_contract(self):
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_EXECUTION_OWNER_RELAY.md").read_text(encoding="utf-8")
        entry = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        self.assertIn("EXACT_TARGET", doc)
        self.assertIn("AMBIGUOUS_TARGET", doc)
        self.assertIn("Wave 64", doc)
        self.assertIn("Wave 49", doc)
        self.assertIn("Wave 48", doc)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No debe interpretarse como W100", entry)
        expected = "Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay"
        self.assertIn(expected, entry)


if __name__ == "__main__":
    unittest.main()
