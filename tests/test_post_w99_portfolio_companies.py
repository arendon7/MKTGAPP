from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.portfolio_companies import SCHEMA, build_portfolio_companies
from binario_marketing.service_post_w99_portfolio_companies_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


def center(*, ready_ids=()):
    labels = {
        "workspace": "Workspace de creación", "meta": "Conexión Meta", "facebook": "Facebook Page",
        "instagram": "Instagram profesional", "ads": "Cuenta publicitaria", "campaign": "Campaña de marketing",
        "creative": "Creative Studio", "crm": "CRM con contactos",
    }
    views = {"workspace": "video", "meta": "companies", "facebook": "companies", "instagram": "companies", "ads": "companies", "campaign": "campaigns", "creative": "content", "crm": "crm"}
    steps = [{"id": key, "label": label, "ready": key in ready_ids, "view": views[key], "internal_marker": "omit-me"} for key, label in labels.items()]
    return {
        "company": {"id": "internal-company", "facebook_page_id": "internal-page", "instagram_id": "internal-ig", "ad_account_id": "internal-ad"},
        "readiness": {"ready": len(ready_ids), "total": 8, "steps": steps},
        "legacy_dashboard": {"internal_marker": "omit-dashboard"},
    }


class PortfolioCompaniesPureTests(unittest.TestCase):
    def test_projection_reuses_w50_and_minimizes_state(self):
        company = SimpleNamespace(id="company_" + "1" * 24, name="Marca Uno")
        payload = build_portfolio_companies([company], {company.id: center(ready_ids={"workspace", "meta", "facebook"})})
        self.assertEqual(payload["schema"], SCHEMA)
        self.assertEqual(payload["summary"]["companies"], 1)
        row = payload["items"][0]
        self.assertEqual(row["readiness"]["ready"], 3)
        self.assertEqual(row["readiness"]["total"], 8)
        self.assertEqual(row["next_action"]["code"], "SETUP_INSTAGRAM")
        self.assertEqual(row["next_action"]["owner"], "W50_SETUP_READINESS")
        serialized = json.dumps(payload)
        for forbidden in ("internal-page", "internal-ig", "internal-ad", "omit-dashboard", "internal_marker", "internal-company"):
            self.assertNotIn(forbidden, serialized)
        self.assertTrue(payload["contracts"]["w50_command_center_is_readiness_authority"])
        self.assertTrue(payload["contracts"]["no_duplicate_readiness_engine"])
        self.assertFalse(payload["safety"]["provider_read_performed"])
        self.assertFalse(payload["safety"]["provider_mutation_performed"])

    def test_ready_and_local_error_states_fail_closed(self):
        ready = SimpleNamespace(id="ready", name="Lista")
        broken = SimpleNamespace(id="broken", name="Con error")
        all_steps = {"workspace", "meta", "facebook", "instagram", "ads", "campaign", "creative", "crm"}
        payload = build_portfolio_companies([ready, broken], {ready.id: center(ready_ids=all_steps), broken.id: {"_local_state_error": True}})
        self.assertEqual(payload["summary"]["fully_ready"], 1)
        self.assertEqual(payload["summary"]["local_state_errors"], 1)
        rows = {row["company"]["id"]: row for row in payload["items"]}
        self.assertEqual(rows["ready"]["status"], "READY")
        self.assertEqual(rows["broken"]["status"], "LOCAL_STATE_ERROR")


class PortfolioCompaniesRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.companies.create("Marca Runtime")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_runtime_and_http_are_local_read_only(self):
        with patch.object(self.runtime, "marketing_command_center", return_value=center(ready_ids={"workspace"})) as command_center:
            payload = self.runtime.portfolio_companies()
            command_center.assert_called_once_with(self.company.id)
            self.assertEqual(payload["schema"], SCHEMA)
            server = create_server(self.runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                root = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(root + "/api/portfolio/companies", timeout=5) as response:
                    api_payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(api_payload["schema"], SCHEMA)
                with urlopen(root + "/portfolio-companies.js", timeout=5) as response:
                    source = response.read().decode("utf-8")
                self.assertIn("POST_W99_PORTFOLIO_COMPANIES", source)
                with urlopen(root + "/portfolio-campaigns.js", timeout=5) as response:
                    chained = response.read().decode("utf-8")
                self.assertIn("/portfolio-companies.js", chained)
            finally:
                server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_does_not_own_setup_mutations_or_provider_endpoints(self):
        source = (ROOT / "web" / "portfolio-companies.js").read_text(encoding="utf-8")
        for required in ("/api/portfolio/companies", "Preparación operativa", "Nueva empresa", "Ver todas las empresas", "baseRefresh"):
            self.assertIn(required, source)
        for forbidden in ("method:'POST'", "method:'PATCH'", "method:'DELETE'", "/api/meta/", "setInterval(", "MutationObserver"):
            self.assertNotIn(forbidden, source)

    def test_terminal_alias_docs_and_workflows(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_companies_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_campaigns_app as base", service)
        self.assertIn("marketing_command_center", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_companies_app", dev)
        docs = (ROOT / "docs" / "POST_W99_COMPANY_ONBOARDING.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("w50", docs.casefold())
        self.assertIn("remote readback", docs.casefold())


if __name__ == "__main__":
    unittest.main()
