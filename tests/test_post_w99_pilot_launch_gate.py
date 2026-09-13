from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_pilot_launch_gate_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotLaunchGateTests(unittest.TestCase):
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

    def test_http_chain_appends_launch_gate_after_recovery_rehearsal(self):
        with urlopen(self.root + "/pilot-recovery-rehearsal.js", timeout=5) as response:
            chained = response.read().decode("utf-8")
        self.assertIn("/pilot-launch-gate.js", chained)
        with urlopen(self.root + "/pilot-launch-gate.js", timeout=5) as response:
            source = response.read().decode("utf-8")
        self.assertIn("POST_W99_PILOT_LAUNCH_GATE", source)
        self.assertIn("Preparación piloto", source)

    def test_gate_reuses_existing_read_only_authorities_and_requires_five_controls(self):
        source = (ROOT / "web" / "pilot-launch-gate.js").read_text(encoding="utf-8")
        self.assertIn("/api/pilot-session/status", source)
        self.assertIn("/api/portfolio/companies", source)
        self.assertIn("Aplicación local", source)
        self.assertIn("Empresas", source)
        self.assertIn("Recorrido observado", source)
        self.assertIn("Respaldo local", source)
        self.assertIn("Recuperación ensayada", source)
        self.assertIn("LISTO PARA PILOTO LOCAL", source)
        self.assertIn("r.snapshot_id===snapshot.latest.id", source)
        self.assertIn("passed===checks.length", source)
        self.assertIn("summary.fully_ready", source)
        self.assertIn("summary.average_percent", source)

    def test_gate_is_explicit_session_only_and_has_no_business_or_release_authority(self):
        source = (ROOT / "web" / "pilot-launch-gate.js").read_text(encoding="utf-8")
        self.assertIn("button.addEventListener('click',async()=>{render();await refresh()})", source)
        self.assertIn("pilotLaunchGateReport", source)
        self.assertIn("release 0.9.0", source)
        for forbidden in (
            "method:'POST'", "method:'PATCH'", "method:'DELETE'", "/api/meta/", "setInterval(",
            "MutationObserver", "localStorage", "restoreSnapshot", "deleteSnapshot", "publish-now",
            "MetaGraphClient", "AIProviderClient", "create_campaign",
        ):
            self.assertNotIn(forbidden, source)

    def test_recovery_evidence_is_memory_only_and_bound_to_latest_snapshot(self):
        source = (ROOT / "web" / "pilot-recovery-rehearsal.js").read_text(encoding="utf-8")
        self.assertIn("pilotRecoveryRehearsalReport", source)
        self.assertIn("post-w99-pilot-recovery-rehearsed", source)
        self.assertIn("pilot-recovery-session-evidence.v1", source)
        self.assertIn("snapshot_id:outcome.snapshot_id", source)
        self.assertIn("active_data_unchanged:true", source)
        self.assertIn("workspace_cleaned:true", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)

    def test_terminal_release_separation_and_documentation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_launch_gate_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_recovery_rehearsal_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        self.assertNotIn("do_POST", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_launch_gate_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_LAUNCH_GATE.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production", docs.casefold())
        self.assertIn("w50", docs.casefold())
        self.assertIn("session", docs.casefold())
        self.assertIn("release", docs.casefold())


if __name__ == "__main__":
    unittest.main()
