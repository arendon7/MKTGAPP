from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.portfolio_content import PORTFOLIO_CONTENT_SCHEMA, build_portfolio_content
from binario_marketing.service_post_w99_portfolio_content_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PortfolioContentPureTests(unittest.TestCase):
    def test_projection_reuses_creative_state_and_minimizes_asset_fields(self):
        first = {"id": "company_" + "1" * 24, "name": "Marca Uno"}
        second = {"id": "company_" + "2" * 24, "name": "Marca Dos"}
        contexts = {
            first["id"]: {
                "items": [
                    {
                        "media": {"id": "media-a", "kind": "image", "original_name": "pieza-a.png", "sha256": "secret-hash", "file_url": "/private/file"},
                        "creative": {"title": "Pieza A", "stage": "READY", "purpose": "ORGANIC", "channels": ["instagram"], "notes": "private creative notes"},
                        "campaign": {"id": "campaign-a", "name": "Campaña A", "status": "ACTIVE", "budget": 999999},
                        "publications": [],
                        "paid_media": [],
                        "effective_stage": "READY",
                    },
                    {
                        "media": {"id": "media-b", "kind": "video", "original_name": "pieza-b.mp4"},
                        "creative": {"title": "Pieza B", "stage": "DRAFT", "channels": []},
                        "campaign": None,
                        "publications": [{"id": "pub-b", "status": "QUEUED", "scheduled_for": "2026-09-12T14:00:00+00:00", "remote_id": "provider-secret"}],
                        "paid_media": [],
                        "effective_stage": "SCHEDULED",
                    },
                ],
                "meta": {"social_ready": True, "ads_ready": False},
            },
            second["id"]: {
                "items": [{"media": {"id": "media-c", "kind": "image", "original_name": "pieza-c.png"}, "creative": None, "campaign": None, "publications": [], "paid_media": [], "effective_stage": "UNPROFILED"}],
                "meta": {"social_ready": False, "ads_ready": False},
            },
        }
        payload = build_portfolio_content([second, first], contexts, generated_at="2026-09-09T12:00:00+00:00")
        self.assertEqual(payload["schema"], PORTFOLIO_CONTENT_SCHEMA)
        self.assertEqual(payload["summary"]["total_assets"], 3)
        self.assertEqual(payload["summary"]["ready"], 1)
        self.assertEqual(payload["summary"]["scheduled"], 1)
        self.assertEqual(payload["summary"]["unprofiled"], 1)
        self.assertEqual([row["stage"] for row in payload["items"]], ["UNPROFILED", "READY", "SCHEDULED"])
        scheduled = next(row for row in payload["items"] if row["stage"] == "SCHEDULED")
        self.assertEqual(scheduled["scheduled_for"], "2026-09-12T14:00:00+00:00")
        self.assertEqual(scheduled["action"], {"label": "Abrir contenido", "view": "content", "media_id": "media-b"})
        serialized = json.dumps(payload)
        for forbidden in ("secret-hash", "/private/file", "private creative notes", "provider-secret", '"budget"', '"remote_id"', '"notes"', '"sha256"'):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(payload["contracts"]["existing_calendar_remains_schedule_authority"])
        self.assertTrue(payload["contracts"]["no_duplicate_scheduler"])

    def test_local_error_is_declared_without_inventing_assets(self):
        company = {"id": "company_" + "3" * 24, "name": "Marca"}
        payload = build_portfolio_content([company], {company["id"]: {"_local_state_error": True, "items": []}})
        self.assertEqual(payload["summary"]["local_state_errors"], 1)
        self.assertEqual(payload["items"], [])
        self.assertEqual(payload["companies"][0]["state"], "LOCAL_STATE_ERROR")


class PortfolioContentRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.companies.create("Marca Runtime")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_runtime_and_http_are_local_read_only(self):
        payload = self.runtime.portfolio_content()
        self.assertEqual(payload["schema"], PORTFOLIO_CONTENT_SCHEMA)
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["content_mutation_performed"])
        self.assertTrue(payload["contracts"]["creative_studio_is_content_state_authority"])
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/api/portfolio/content", timeout=5) as response:
                api_payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(api_payload["schema"], PORTFOLIO_CONTENT_SCHEMA)
            with urlopen(root + "/portfolio-content.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_PORTFOLIO_CONTENT", source)
            with urlopen(root + "/portfolio-crm.js", timeout=5) as response:
                chained = response.read().decode("utf-8")
            self.assertIn("/portfolio-content.js", chained)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_contract_delegates_mutation_and_reuses_global_calendar(self):
        source = (ROOT / "web" / "portfolio-content.js").read_text(encoding="utf-8")
        for required in ("CONTENIDO / MULTIEMPRESA", "/api/portfolio/content", "portfolioNavigate", "Calendario global", "Volver a todas las empresas", "refreshMarketingOps", "opsShowView('calendar')"):
            self.assertIn(required, source)
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'DELETE'", "setInterval(", "MutationObserver", "fetch('https://", 'fetch("https://'):
            self.assertNotIn(forbidden, source)

    def test_dev_alias_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_content_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_crm_app as base", service)
        self.assertIn("/api/portfolio/content", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_content_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PORTFOLIO_CONTENT.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("calendario ya es multiempresa", docs.casefold())


if __name__ == "__main__":
    unittest.main()
