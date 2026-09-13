from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_pilot_health_summary_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotHealthSummaryHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_static_chain_loads_health_after_incident_log(self):
        with urlopen(self.root + "/pilot-incident-log.js", timeout=5) as response:
            parent = response.read().decode("utf-8")
        self.assertIn("/pilot-health-summary.js", parent)
        self.assertIn("data-post-w99-pilot-health-summary", parent)
        with urlopen(self.root + "/pilot-health-summary.js", timeout=5) as response:
            source = response.read().decode("utf-8")
        self.assertIn("Salud del piloto", source)
        self.assertIn("/api/pilot/daily-receipts?limit=90", source)
        self.assertIn("/api/pilot/incidents?status=ALL&limit=100", source)

    def test_existing_local_read_models_remain_the_only_health_inputs(self):
        with urlopen(self.root + "/api/pilot/daily-receipts?limit=90", timeout=5) as response:
            receipts = json.loads(response.read().decode("utf-8"))
        with urlopen(self.root + "/api/pilot/incidents?status=ALL&limit=100", timeout=5) as response:
            incidents = json.loads(response.read().decode("utf-8"))
        self.assertEqual(receipts["summary"]["days_observed"], 0)
        self.assertEqual(incidents["summary"]["incident_count"], 0)
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_health_summary_app.py").read_text(encoding="utf-8")
        self.assertNotIn("/api/pilot/health", service)
        self.assertNotIn("def do_POST", service)
        self.assertNotIn("def do_DELETE", service)

    def test_health_rules_are_explicit_conservative_and_not_ai_scored(self):
        source = (ROOT / "web" / "pilot-health-summary.js").read_text(encoding="utf-8")
        self.assertIn("if(blocking>0)", source)
        self.assertIn("status='BLOCKED'", source)
        self.assertIn("status='NO_EVIDENCE'", source)
        self.assertIn("status='ATTENTION'", source)
        self.assertIn("status='STABLE'", source)
        self.assertIn("recentAttention", source)
        self.assertIn("todayReceipt", source)
        self.assertIn("No es un puntaje de IA", source)
        self.assertIn("La clasificación es informativa y local", source)

    def test_browser_layer_is_explicit_get_only_and_provider_free(self):
        source = (ROOT / "web" / "pilot-health-summary.js").read_text(encoding="utf-8")
        self.assertIn("method:'GET'", source)
        self.assertIn("cache:'no-store'", source)
        self.assertIn("post-w99-pilot-launch-gate-rendered", source)
        self.assertIn("Seguimiento 30 días", source)
        self.assertIn("Incidencias", source)
        for forbidden in (
            "method:'POST'", "method:'PATCH'", "method:'PUT'", "method:'DELETE'",
            "X-Mercadeo-Operator", "setInterval(", "MutationObserver", "localStorage", "sessionStorage",
            "/api/meta/", "MetaGraphClient", "AIProviderClient", "publish-now", "restoreSnapshot",
            "createSnapshot", "scorePilot", "fetch('https://", 'fetch("https://',
        ):
            self.assertNotIn(forbidden, source)

    def test_terminal_release_and_main_boundaries(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_health_summary_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_incident_log_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_incident_log_app", dev)
        self.assertIn("service_post_w99_pilot_health_summary_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_HEALTH_SUMMARY.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production readiness", docs.casefold())
        self.assertIn("read-only", docs.casefold())
        self.assertIn("no new api", docs.casefold())


if __name__ == "__main__":
    unittest.main()
