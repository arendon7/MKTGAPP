from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_pilot_guidance_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotGuidanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_guidance_is_served_after_pilot_readiness(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/pilot-readiness.js", timeout=5) as response:
                readiness = response.read().decode("utf-8")
            self.assertIn("/pilot-guidance.js", readiness)
            self.assertIn("data-post-w99-pilot-guidance", readiness)
            with urlopen(root + "/pilot-guidance.js", timeout=5) as response:
                guidance = response.read().decode("utf-8")
            self.assertIn("POST_W99_PILOT_GUIDANCE", guidance)
            self.assertIn("/api/portfolio/companies", guidance)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_browser_contract_reuses_w50_projection_without_provider_reads_or_mutations(self):
        source = (ROOT / "web" / "pilot-guidance.js").read_text(encoding="utf-8")
        for required in (
            "/api/portfolio/companies",
            "readiness.steps",
            "next_action",
            "Preparación operativa incompleta",
            "Siguiente paso pendiente",
            "opsShowView(view)",
            "refreshMarketingOps(view==='companies')",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "/api/meta/",
            "method:'POST'",
            "method:'PATCH'",
            "method:'DELETE'",
            "setInterval(",
            "MutationObserver",
            "MetaGraphClient",
            "AIProviderClient",
            "W50_STEP_ORDER",
            "SETUP_STEP_IDS",
        ):
            self.assertNotIn(forbidden, source)

    def test_guidance_only_acts_for_an_exact_company_and_known_pilot_views(self):
        source = (ROOT / "web" / "pilot-guidance.js").read_text(encoding="utf-8")
        self.assertIn("marketingOpsState.selectedCompanyId", source)
        for view in ("inbox", "publish", "campaigns", "pauta", "intelligence", "content", "crm", "calendar"):
            self.assertIn(f"'{view}'", source)
        self.assertIn("LOCAL_STATE_ERROR", source)
        self.assertIn("Reintentar lectura local", source)

    def test_terminal_alias_and_release_separation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_guidance_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_readiness_app as base", service)
        self.assertIn("/pilot-guidance.js", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_guidance_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_GUIDANCE.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("W50", docs)
        self.assertIn("not production", docs.casefold())


if __name__ == "__main__":
    unittest.main()
