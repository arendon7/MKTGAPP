import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen

from binario_marketing.service_wave67_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave67PhysicalUATHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name) / "data"
        self.runtime = AppRuntime.create(ROOT, self.data_root)
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _start(self, *, github_actions="true", system="Darwin", machine="arm64"):
        with patch("binario_marketing.physical_uat_store.platform.system", return_value=system), \
             patch("binario_marketing.physical_uat_store.platform.machine", return_value=machine), \
             patch("binario_marketing.physical_uat_store.platform.mac_ver", return_value=("15.7.7", ("", "", ""), "")), \
             patch.dict(os.environ, {"GITHUB_ACTIONS": github_actions}, clear=False):
            return self.runtime.start_physical_uat(self.company["id"], {"operator": "Agustin UAT"})

    def _resolve_required(self, session, status="PASS"):
        current = session
        for scenario in session["scenarios"]:
            if scenario["required"]:
                current = self.runtime.update_physical_uat_scenario(
                    self.company["id"], session["id"], scenario["id"],
                    {"status": status, "note": f"evidence {scenario['id']}"},
                )
        return current

    @staticmethod
    def _request_json(url, *, method="GET", body=None):
        data = None if body is None else json.dumps(body).encode("utf-8")
        request = Request(url, method=method, data=data)
        if data is not None:
            request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_ci_arm64_session_can_pass_logic_but_never_satisfies_physical_gate(self):
        session = self._start(github_actions="true", system="Darwin", machine="arm64")
        self.assertTrue(session["machine"]["is_ci"])
        self.assertFalse(session["machine"]["physical_gate_eligible"])
        self._resolve_required(session, "PASS")
        finished = self.runtime.finish_physical_uat(self.company["id"], session["id"])
        self.assertEqual(finished["status"], "PASSED")
        self.assertFalse(finished["physical_uat_complete"])
        self.assertRegex(finished["evidence_sha256"], r"^[0-9a-f]{64}$")
        report = self.runtime.physical_uat_report(self.company["id"], session["id"])
        self.assertFalse(report["summary"]["physical_gate_eligible"])
        self.assertFalse(report["summary"]["physical_uat_complete"])
        self.assertFalse(report["release_boundary"]["release_ready"])

    def test_real_darwin_arm64_outside_ci_is_eligible_but_does_not_open_release(self):
        session = self._start(github_actions="", system="Darwin", machine="arm64")
        self.assertTrue(session["machine"]["physical_gate_eligible"])
        self._resolve_required(session, "PASS")
        finished = self.runtime.finish_physical_uat(self.company["id"], session["id"])
        self.assertTrue(finished["physical_uat_complete"])
        overview = self.runtime.physical_uat_overview(self.company["id"])
        self.assertTrue(overview["physical_uat_complete"])
        self.assertFalse(overview["release_boundary"]["release_ready"])
        self.assertFalse(overview["release_boundary"]["distribution_signing_certified"])
        self.assertFalse(overview["release_boundary"]["notarization_certified"])
        self.assertFalse(overview["release_boundary"]["production_ready"])

    def test_fail_and_blocked_sessions_never_complete_physical_gate(self):
        failed = self._start(github_actions="", system="Darwin", machine="arm64")
        first = next(row for row in failed["scenarios"] if row["required"])
        self.runtime.update_physical_uat_scenario(self.company["id"], failed["id"], first["id"], {"status": "FAIL", "note": "observed defect"})
        for scenario in failed["scenarios"]:
            if scenario["required"] and scenario["id"] != first["id"]:
                self.runtime.update_physical_uat_scenario(self.company["id"], failed["id"], scenario["id"], {"status": "PASS"})
        failed_done = self.runtime.finish_physical_uat(self.company["id"], failed["id"])
        self.assertEqual(failed_done["status"], "FAILED")
        self.assertFalse(failed_done["physical_uat_complete"])

        blocked = self._start(github_actions="", system="Darwin", machine="arm64")
        first = next(row for row in blocked["scenarios"] if row["required"])
        self.runtime.update_physical_uat_scenario(self.company["id"], blocked["id"], first["id"], {"status": "BLOCKED"})
        for scenario in blocked["scenarios"]:
            if scenario["required"] and scenario["id"] != first["id"]:
                self.runtime.update_physical_uat_scenario(self.company["id"], blocked["id"], scenario["id"], {"status": "PASS"})
        blocked_done = self.runtime.finish_physical_uat(self.company["id"], blocked["id"])
        self.assertEqual(blocked_done["status"], "BLOCKED")
        self.assertFalse(blocked_done["physical_uat_complete"])

    def test_required_scenarios_cannot_be_skipped_pending_blocks_finish_and_active_is_unique(self):
        session = self._start()
        with self.assertRaises(ValueError):
            self._start()
        required = next(row for row in session["scenarios"] if row["required"])
        optional = next(row for row in session["scenarios"] if not row["required"])
        with self.assertRaises(ValueError):
            self.runtime.update_physical_uat_scenario(self.company["id"], session["id"], required["id"], {"status": "SKIPPED"})
        skipped = self.runtime.update_physical_uat_scenario(self.company["id"], session["id"], optional["id"], {"status": "SKIPPED", "note": "provider not configured"})
        self.assertEqual(next(row for row in skipped["scenarios"] if row["id"] == optional["id"])["status"], "SKIPPED")
        with self.assertRaises(ValueError):
            self.runtime.finish_physical_uat(self.company["id"], session["id"])

    def test_session_persists_atomically_and_is_company_scoped(self):
        session = self._start()
        other = self.runtime.create_company({"name": "Otra"})
        with self.assertRaises(KeyError):
            self.runtime.physical_uat_report(other["id"], session["id"])
        second = AppRuntime.create(ROOT, self.data_root)
        try:
            overview = second.physical_uat_overview(self.company["id"])
            self.assertEqual(overview["active_session"]["id"], session["id"])
            self.assertEqual(overview["active_session"]["operator"], "Agustin UAT")
            path = self.data_root / "physical_uat" / self.company["id"] / f"{session['id']}.json"
            self.assertTrue(path.is_file())
            json.loads(path.read_text(encoding="utf-8"))
        finally:
            if second.social_scheduler is not None:
                second.social_scheduler.shutdown()
            second.proxies.shutdown(); second.transcriptions.shutdown(); second.renders.shutdown()

    def test_http_exposes_only_explicit_uat_evidence_mutations(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/uat-readiness.js", timeout=5) as response:
                bootstrap = response.read().decode("utf-8")
            self.assertIn("physical-uat.js", bootstrap)
            self.assertIn("data-physical-uat-wave67", bootstrap)
            with urlopen(base + "/physical-uat.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Evidencia de prueba en Mac físico", ui)
            status, session = self._request_json(base + f"/api/companies/{self.company['id']}/physical-uat", method="POST", body={"operator": "HTTP UAT"})
            self.assertEqual(status, 201)
            scenario = next(row for row in session["scenarios"] if row["required"])
            status, updated = self._request_json(
                base + f"/api/companies/{self.company['id']}/physical-uat/{session['id']}/scenarios/{scenario['id']}",
                method="PATCH", body={"status": "PASS", "note": "HTTP evidence"},
            )
            self.assertEqual(status, 200)
            self.assertEqual(next(row for row in updated["scenarios"] if row["id"] == scenario["id"])["status"], "PASS")
            status, overview = self._request_json(base + f"/api/companies/{self.company['id']}/physical-uat")
            self.assertEqual(status, 200)
            self.assertEqual(overview["schema"], "binario.marketing.physical-uat-overview.v1")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_frontend_has_manual_evidence_actions_but_no_marketing_or_background_authority(self):
        ui = (ROOT / "web" / "physical-uat.js").read_text(encoding="utf-8")
        for marker in (
            "Evidencia de prueba en Mac físico",
            "CI nunca podrá satisfacer el gate físico",
            "Iniciar UAT física",
            "Cerrar sesión",
            "Exportar JSON",
            "method:'POST'",
            "method:'PATCH'",
            "queueMicrotask",
        ):
            self.assertIn(marker, ui)
        for forbidden in (
            "setInterval",
            "sendBeacon",
            "fetch('https://",
            "/opportunities",
            "/publications",
            "/paid-media",
            "/ai/generate",
            "supabase",
            "vercel",
        ):
            self.assertNotIn(forbidden, ui.lower() if forbidden in {"supabase", "vercel"} else ui)

    def test_builder_audit_workflows_and_release_boundary_remain_unchanged(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        service = (ROOT / "src" / "binario_marketing" / "service_wave67_app.py").read_text(encoding="utf-8")
        store = (ROOT / "src" / "binario_marketing" / "physical_uat_store.py").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_wave67_physical_uat_harness.sh").read_text(encoding="utf-8")
        self.assertIn("'service_wave65_app','service_wave66_app')", builder)
        self.assertIn("line='from binario_marketing.service_wave67_app import serve", builder)
        self.assertIn("audit_wave66_product_uat_readiness.sh", builder)
        self.assertIn("audit_wave67_physical_uat_harness.sh", builder)
        self.assertLess(builder.index("audit_wave66_product_uat_readiness.sh"), builder.index("service_wave67_app import serve"))
        for wave in (59, 60, 61, 62, 63, 64, 65, 66, 67):
            self.assertIn(f"CURRENT ARM64 ITERATION BUILD PASS: Wave {wave}", builder)
        self.assertIn("service_wave66_app as base", service)
        self.assertIn("physical.src='/physical-uat.js'", service)
        self.assertIn("GITHUB_ACTIONS", store)
        self.assertIn("physical_gate_eligible", store)
        self.assertIn("release_authority", store)
        self.assertIn("WAVE 67 PHYSICAL UAT EVIDENCE HARNESS AUDIT PASS", audit)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)


if __name__ == "__main__":
    unittest.main()
