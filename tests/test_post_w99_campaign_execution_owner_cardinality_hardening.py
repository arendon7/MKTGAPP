import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_campaign_execution_owner_cardinality_hardening_app import (
    AppRuntime,
    _harden_media_resolution,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


def creative(media_id: str, stage: str) -> dict:
    return {
        "media": {"id": media_id, "original_name": f"{media_id}.png"},
        "creative": {"title": media_id},
        "effective_stage": stage,
    }


class PostW99CampaignExecutionOwnerCardinalityHardeningTests(unittest.TestCase):
    def _shutdown_runtime(self, runtime):
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_finish_creative_multiple_incomplete_is_ambiguous_even_when_w64_selected_one(self):
        inherited = {"state": "EXACT_TARGET", "target_id": "draft-a"}
        resolution = _harden_media_resolution(
            next_action={"code": "FINISH_CREATIVE", "media_id": "draft-a"},
            linked_creatives=[creative("draft-a", "DRAFT"), creative("draft-b", "BRIEF")],
            inherited_resolution=inherited,
        )
        self.assertEqual(resolution["state"], "AMBIGUOUS_TARGET")
        self.assertIsNone(resolution["target_id"])
        self.assertEqual(resolution["candidate_count"], 2)
        self.assertEqual({row["id"] for row in resolution["candidates"]}, {"draft-a", "draft-b"})
        self.assertIn("posicional", resolution["reason"])

    def test_prepare_distribution_multiple_ready_is_ambiguous_even_when_w64_selected_one(self):
        resolution = _harden_media_resolution(
            next_action={"code": "PREPARE_DISTRIBUTION", "media_id": "ready-a"},
            linked_creatives=[creative("ready-a", "READY"), creative("ready-b", "SCHEDULED")],
            inherited_resolution={"state": "EXACT_TARGET", "target_id": "ready-a"},
        )
        self.assertEqual(resolution["state"], "AMBIGUOUS_TARGET")
        self.assertIsNone(resolution["target_id"])
        self.assertEqual(resolution["candidate_count"], 2)

    def test_unique_semantic_candidate_can_be_exact_while_ineligible_rows_do_not_contaminate(self):
        finish = _harden_media_resolution(
            next_action={"code": "FINISH_CREATIVE", "media_id": "draft-only"},
            linked_creatives=[creative("draft-only", "DRAFT"), creative("ready-other", "READY")],
            inherited_resolution={},
        )
        self.assertEqual((finish["state"], finish["target_id"]), ("EXACT_TARGET", "draft-only"))
        self.assertEqual(finish["candidate_count"], 1)

        distribute = _harden_media_resolution(
            next_action={"code": "PREPARE_DISTRIBUTION", "media_id": "ready-only"},
            linked_creatives=[creative("ready-only", "READY"), creative("draft-other", "DRAFT")],
            inherited_resolution={},
        )
        self.assertEqual((distribute["state"], distribute["target_id"]), ("EXACT_TARGET", "ready-only"))
        self.assertEqual(distribute["candidate_count"], 1)

    def test_unique_semantic_candidate_must_match_w64_media_id(self):
        resolution = _harden_media_resolution(
            next_action={"code": "FINISH_CREATIVE", "media_id": "stale-media"},
            linked_creatives=[creative("actual-draft", "DRAFT"), creative("ready-other", "READY")],
            inherited_resolution={},
        )
        self.assertEqual(resolution["state"], "NO_TARGET")
        self.assertIsNone(resolution["target_id"])
        self.assertEqual(resolution["candidate_count"], 1)
        self.assertIn("no coincide", resolution["reason"])

    def test_non_media_codes_preserve_parent_resolution(self):
        inherited = {"state": "EXACT_TARGET", "target_kind": "PUBLICATION", "target_id": "pub-1"}
        resolution = _harden_media_resolution(
            next_action={"code": "FIX_PUBLICATION"},
            linked_creatives=[creative("draft", "DRAFT")],
            inherited_resolution=inherited,
        )
        self.assertEqual(resolution, inherited)
        self.assertIsNot(resolution, inherited)

    def test_runtime_turns_positional_finish_creative_into_ambiguity(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            try:
                company = runtime.create_company({"name": "Cardinality Co"})
                campaign = runtime.campaigns.create(company["id"], {
                    "name": "Dos borradores",
                    "objective": "LEADS",
                    "status": "IN_PROGRESS",
                    "channels": ["facebook_page"],
                })
                for index in range(2):
                    payload = b"\x89PNG\r\n\x1a\ncardinality" + bytes([index])
                    media = runtime.upload_company_media(company["id"], f"draft-{index}.png", "image", io.BytesIO(payload), len(payload))
                    runtime.upsert_company_creative(company["id"], media["id"], {
                        "title": f"Draft {index}",
                        "stage": "DRAFT",
                        "purpose": "LEADS",
                        "campaign_id": campaign.id,
                        "channels": ["facebook_page"],
                    })
                context = runtime.campaign_execution_owner_context(company["id"], campaign.id)
                self.assertEqual(context["execution"]["next_action"]["code"], "FINISH_CREATIVE")
                self.assertEqual(context["resolution"]["state"], "AMBIGUOUS_TARGET")
                self.assertEqual(context["resolution"]["candidate_count"], 2)
                self.assertTrue(context["contracts"]["media_identity_requires_semantic_cardinality"])
                self.assertTrue(context["contracts"]["w64_positional_media_id_is_not_identity_authority"])

                rows = [row for row in runtime.action_center(company["id"])["queue"] if row.get("kind") == "finish_creative"]
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["owner_resolution"]["state"], "AMBIGUOUS_TARGET")
                self.assertEqual(rows[0]["action"]["view"], "content")
            finally:
                self._shutdown_runtime(runtime)

    def test_browser_hardening_preserves_canonical_submit_invariants(self):
        source = (ROOT / "web" / "campaign-execution-owner-cardinality-hardening.js").read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count("controlHandoffSingleGroup"), 4)
        self.assertIn("Guardar ficha creativa", source)
        self.assertIn("Guardar cambios", source)
        self.assertIn("W49_FINISH_CREATIVE_CANONICAL_SUBMIT", source)
        self.assertIn("W35_DEFINE_CHANNELS_CANONICAL_SUBMIT", source)
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

    def test_http_bootstrap_is_static_only_and_inherits_parent_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            company = runtime.create_company({"name": "Hardening HTTP"})
            campaign = runtime.campaigns.create(company["id"], {"name": "Exact", "objective": "LEADS", "status": "IN_PROGRESS", "channels": []})
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            root = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                parent = urlopen(root + "/campaign-execution-owner-relay.js", timeout=5).read().decode("utf-8")
                hardening = urlopen(root + "/campaign-execution-owner-cardinality-hardening.js", timeout=5).read().decode("utf-8")
                context = json.loads(urlopen(root + f"/api/companies/{company['id']}/campaigns/{campaign.id}/execution-owner-context", timeout=5).read().decode("utf-8"))
                self.assertIn("campaign-execution-owner-cardinality-hardening.js", parent)
                self.assertIn("data-post-w99-campaign-execution-owner-cardinality-hardening", parent)
                self.assertIn("Guardar ficha creativa", hardening)
                self.assertEqual(context["schema"], "binario.marketing.campaign-execution-owner-context.v1")
            finally:
                server.shutdown()
                thread.join(timeout=5)
                server.server_close()
                self._shutdown_runtime(runtime)

    def test_service_and_docs_preserve_frozen_release_boundary(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_campaign_execution_owner_cardinality_hardening_app.py").read_text(encoding="utf-8")
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        doc = (ROOT / "docs" / "POST_W99_CAMPAIGN_EXECUTION_OWNER_CARDINALITY_HARDENING.md").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_campaign_execution_owner_relay_app", service)
        self.assertIn("service_post_w99_campaign_execution_owner_cardinality_hardening_app", entrypoint)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_PATCH", service)
        self.assertNotIn("def do_PUT", service)
        self.assertNotIn("def do_DELETE", service)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", doc)
        self.assertIn("No constituye W100", doc)
        self.assertIn("physical uat", doc.lower())


if __name__ == "__main__":
    unittest.main()
