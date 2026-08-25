import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_execution_owner_relay_app import (
    AppRuntime,
    compose_execution_owner_target,
    create_server,
)


ROOT = Path(__file__).resolve().parents[1]


class PostW99ExecutionOwnerRelayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Relay Company"})
        self.runtime.companies.update(self.company["id"], {
            "facebook_page_id": "111111111111",
            "facebook_page_name": "Relay",
            "instagram_id": "222222222222",
            "instagram_username": "relay",
            "ad_account_id": "333333333333",
            "ad_account_name": "Relay Ads",
        })

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _campaign(self, name="Relay Campaign", channels=None):
        return self.runtime.create_campaign(self.company["id"], {
            "name": name,
            "objective": "LEADS",
            "status": "PLANNING",
            "channels": channels if channels is not None else ["facebook_page", "paid_media"],
        })

    def _image(self, name="relay.png"):
        payload = b"\x89PNG\r\n\x1a\npost-w99-relay"
        return self.runtime.upload_company_media(
            self.company["id"], name, "image", io.BytesIO(payload), len(payload)
        )

    def _creative(self, campaign, *, stage="READY", name="Relay Creative"):
        media = self._image(name.replace(" ", "-").lower() + ".png")
        self.runtime.upsert_company_creative(self.company["id"], media["id"], {
            "title": name,
            "stage": stage,
            "purpose": "LEADS",
            "campaign_id": campaign["id"],
            "channels": ["facebook_page", "paid_media"],
            "primary_copy": "Mensaje relay",
            "public_media_url": "https://cdn.example.com/relay.png",
            "destination_url": "https://example.com/relay",
        })
        return media

    def _paid_draft(self, campaign, media):
        return self.runtime.create_company_paid_media(self.company["id"], {
            "campaign_id": campaign["id"],
            "source_kind": "company_media",
            "company_media_id": media["id"],
            "campaign_name": "Relay Meta",
            "campaign_objective": "OUTCOME_LEADS",
            "special_ad_categories": [],
            "adset_name": "Relay Ad Set",
            "daily_budget": 10000,
            "optimization_goal": "LINK_CLICKS",
            "targeting": {"geo_locations": {"countries": ["CO"]}, "age_min": 25, "age_max": 55},
            "creative_name": "Relay Creative",
            "message": "Mensaje relay",
            "link_url": "https://example.com/relay",
            "call_to_action": "LEARN_MORE",
            "ad_name": "Relay Ad",
        })

    def test_pure_publication_resolution_requires_unique_failed_identity(self):
        unique = compose_execution_owner_target(
            action_code="FIX_PUBLICATION",
            campaign_id="cmp-1",
            creatives=[],
            publications=[{"id": "pub-1", "status": "FAILED"}],
            paid_media=[],
        )
        self.assertEqual(unique["state"], "TARGET_RESOLVED")
        self.assertEqual(unique["target"]["target_kind"], "PUBLICATION")
        self.assertEqual(unique["target"]["target_id"], "pub-1")

        ambiguous = compose_execution_owner_target(
            action_code="FIX_PUBLICATION",
            campaign_id="cmp-1",
            creatives=[],
            publications=[
                {"id": "pub-1", "status": "FAILED"},
                {"id": "pub-2", "status": "FAILED"},
            ],
            paid_media=[],
        )
        self.assertEqual(ambiguous["state"], "TARGET_AMBIGUOUS")
        self.assertIsNone(ambiguous["target"])
        self.assertEqual(ambiguous["candidate_count"], 2)

    def test_finish_creative_never_uses_first_candidate_when_multiple_are_incomplete(self):
        result = compose_execution_owner_target(
            action_code="FINISH_CREATIVE",
            campaign_id="cmp-1",
            creatives=[
                {"media": {"id": "m-1"}, "effective_stage": "DRAFT"},
                {"media": {"id": "m-2"}, "effective_stage": "BRIEF"},
            ],
            publications=[],
            paid_media=[],
        )
        self.assertEqual(result["state"], "TARGET_AMBIGUOUS")
        self.assertIsNone(result["target"])
        self.assertEqual(result["candidate_count"], 2)

    def test_runtime_resolves_unique_draft_publication_without_provider_read(self):
        campaign = self._campaign(channels=["facebook_page"])
        media = self._creative(campaign)
        prepared = self.runtime.prepare_creative_publication(
            self.company["id"], media["id"], {"channel": "facebook_page"}
        )
        self.assertEqual(prepared["publication"]["status"], "DRAFT")

        payload = self.runtime.execution_owner_context(self.company["id"], campaign["id"])
        self.assertEqual(payload["schema"], "binario.marketing.execution-owner-relay.v1")
        self.assertEqual(payload["execution_next_action"]["code"], "SCHEDULE_OR_PUBLISH")
        self.assertEqual(payload["resolution"]["state"], "TARGET_RESOLVED")
        self.assertEqual(payload["resolution"]["target"]["target_id"], prepared["publication"]["id"])
        self.assertTrue(payload["contracts"]["no_first_candidate_guessing"])
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["business_mutation_performed"])

    def test_runtime_resolves_unique_paid_draft_and_preserves_paused_owner(self):
        campaign = self._campaign()
        media = self._creative(campaign)
        paid = self._paid_draft(campaign, media)
        self.assertEqual(paid["status"], "DRAFT")

        payload = self.runtime.execution_owner_context(self.company["id"], campaign["id"])
        self.assertEqual(payload["execution_next_action"]["code"], "REVIEW_PAID")
        self.assertEqual(payload["resolution"]["state"], "TARGET_RESOLVED")
        self.assertEqual(payload["resolution"]["target"]["target_kind"], "PAID_MEDIA")
        self.assertEqual(payload["resolution"]["target"]["target_id"], paid["id"])
        self.assertFalse(payload["contracts"]["business_mutation_authority"])

    def test_runtime_fails_closed_for_multiple_ready_creatives(self):
        campaign = self._campaign(channels=["facebook_page"])
        self._creative(campaign, name="Creative A")
        self._creative(campaign, name="Creative B")
        payload = self.runtime.execution_owner_context(self.company["id"], campaign["id"])
        self.assertEqual(payload["execution_next_action"]["code"], "PREPARE_DISTRIBUTION")
        self.assertEqual(payload["resolution"]["state"], "TARGET_AMBIGUOUS")
        self.assertEqual(payload["resolution"]["candidate_count"], 2)
        self.assertIsNone(payload["resolution"]["target"])

    def test_company_scope_fails_closed(self):
        campaign = self._campaign()
        other = self.runtime.create_company({"name": "Other"})
        with self.assertRaises(KeyError):
            self.runtime.execution_owner_context(other["id"], campaign["id"])

    def test_http_get_and_bootstrap_append_after_campaign_results_owner(self):
        campaign = self._campaign(channels=["facebook_page"])
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/campaign-results-owner-handoff.js", timeout=5) as response:
                parent = response.read().decode("utf-8")
            self.assertIn("execution-owner-relay.js", parent)
            self.assertIn("data-post-w99-execution-owner-relay", parent)

            with urlopen(base + "/execution-owner-relay.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("PLAN DE HOY · OWNER RELAY", ui)

            with urlopen(
                base + f"/api/companies/{self.company['id']}/campaigns/{campaign['id']}/execution-owner-context",
                timeout=5,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.execution-owner-relay.v1")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_browser_relay_is_navigation_only_and_preserves_human_owner_controls(self):
        ui = (ROOT / "web" / "execution-owner-relay.js").read_text(encoding="utf-8")
        for marker in (
            "TARGET_RESOLVED",
            "TARGET_AMBIGUOUS",
            "Crear en Meta · PAUSED",
            "Cancelar borrador",
            "Guardar ficha creativa",
            "Preparar Facebook",
            "Preparar Instagram",
            "Enviar a Pauta",
            "fix_execution",
            "fix_publication",
        ):
            self.assertIn(marker, ui)
        for forbidden in (
            "method:'POST'",
            'method:"POST"',
            "method:'PATCH'",
            "method:'PUT'",
            "method:'DELETE'",
            "setInterval",
            ".click()",
            "dispatchEvent",
            "sendBeacon",
        ):
            self.assertNotIn(forbidden, ui)
        self.assertIn("opsShowView(context.owner_view)", ui)
        self.assertIn("unique_target_required", (ROOT / "docs" / "POST_W99_EXECUTION_OWNER_RELAY.md").read_text(encoding="utf-8"))

    def test_dev_terminal_and_frozen_release_boundary_are_explicit(self):
        entrypoint = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "POST_W99_DEV_ENTRYPOINT.md").read_text(encoding="utf-8")
        relay_docs = (ROOT / "docs" / "POST_W99_EXECUTION_OWNER_RELAY.md").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_execution_owner_relay_app", entrypoint)
        self.assertIn("Execution Owner Relay", docs)
        self.assertIn("Campaign Results Owner Handoff → Execution Owner Relay", docs)
        self.assertIn("main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", relay_docs)
        self.assertIn("No constituye W100", relay_docs)
        self.assertIn("physical UAT", relay_docs.lower())


if __name__ == "__main__":
    unittest.main()
