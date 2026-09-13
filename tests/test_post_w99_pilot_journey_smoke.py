from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_pilot_journey_smoke_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotJourneySmokeTests(unittest.TestCase):
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

    def test_smoke_script_is_loaded_after_pilot_guidance(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/pilot-guidance.js", timeout=5) as response:
                guidance = response.read().decode("utf-8")
            self.assertIn("/pilot-journey-smoke.js", guidance)
            self.assertIn("data-post-w99-pilot-journey-smoke", guidance)
            with urlopen(root + "/pilot-journey-smoke.js", timeout=5) as response:
                smoke = response.read().decode("utf-8")
            self.assertIn("POST_W99_PILOT_JOURNEY_SMOKE", smoke)
            self.assertIn("binario.marketing.pilot-journey-smoke.v1", smoke)
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_current_pilot_route_contract_replaces_legacy_semantics(self):
        source = (ROOT / "web" / "pilot-journey-smoke.js").read_text(encoding="utf-8")
        for view in (
            "today-execution", "companies", "inbox", "crm", "content", "calendar",
            "campaigns", "pauta", "intelligence", "publish",
        ):
            self.assertIn(f"view:'{view}'", source)
        self.assertIn("label:'Resultados'", source)
        self.assertIn("requiresCompany:true", source)
        self.assertNotIn("opsShowLegacy", source)
        self.assertNotIn("PROJECT_REQUIRED", source)
        self.assertNotIn("WAVE73_VIEWS", source)
        self.assertNotIn("view:'video'", source)
        self.assertNotIn("view:'analytics'", source)

    def test_smoke_is_passive_and_has_no_network_or_business_side_effects(self):
        source = (ROOT / "web" / "pilot-journey-smoke.js").read_text(encoding="utf-8")
        for required in (
            "automaticNavigation:false",
            "providerReads:false",
            "providerMutations:false",
            "formSubmission:false",
            "publishing:false",
            "backgroundPolling:false",
            "Ruta declarada; todavía no fue visitada",
            "Abre cada paso manualmente",
            "globalThis.wave73RunJourneyCheck=pilotJourneyShow",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "fetch(", "opsApi(", "/api/", "method:'POST'", "method:'PATCH'", "method:'DELETE'",
            "setInterval(", "MutationObserver", ".submit(", "requestSubmit(", "publish-now",
            "MetaGraphClient", "AIProviderClient",
        ):
            self.assertNotIn(forbidden, source)
        self.assertEqual(source.count("globalThis.opsShowView(row.view)"), 1)
        self.assertIn("open.addEventListener('click',()=>pilotJourneyOpen(row))", source)

    def test_smoke_records_portfolio_and_company_evidence_separately(self):
        source = (ROOT / "web" / "pilot-journey-smoke.js").read_text(encoding="utf-8")
        self.assertIn("visits:{PORTFOLIO:{},COMPANY:{}}", source)
        self.assertIn("function opsState()", source)
        self.assertIn("opsState()?.selectedCompanyId?'COMPANY':'PORTFOLIO'", source)
        self.assertIn("OWNER_ONLY", source)
        self.assertIn("post-w99-pilot-journey-observed", source)
        self.assertIn("setTimeout(()=>inspect(view),350)", source)

    def test_terminal_alias_and_release_separation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_journey_smoke_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_guidance_app as base", service)
        self.assertIn("/pilot-journey-smoke.js", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_journey_smoke_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_JOURNEY_SMOKE.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production", docs.casefold())
        self.assertIn("no realiza navegación automática", docs.casefold())


if __name__ == "__main__":
    unittest.main()
