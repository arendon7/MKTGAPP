import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service_wave69_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave69PhysicalUATPreflightTests(unittest.TestCase):
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

    @staticmethod
    def _eligible_machine():
        return {
            "system": "Darwin",
            "macos_version": "15.7.7",
            "machine": "arm64",
            "is_ci": False,
            "physical_gate_eligible": True,
        }

    def _fake_packaged_runtime(self, *, main_candidate=True):
        resources = Path(self.tmp.name) / "Bundle" / "Contents" / "Resources"
        source = resources / "source"
        source.mkdir(parents=True)
        runtime = resources / "runtime"
        executables = [
            runtime / "python" / "bin" / "python3",
            runtime / "media" / "bin" / "ffmpeg",
            runtime / "media" / "bin" / "ffprobe",
            runtime / "transcription" / "bin" / "whisper-cli",
        ]
        for path in executables:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("stub", encoding="utf-8")
            path.chmod(0o755)
        manifest = runtime / "transcription" / "RUNTIME.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"engine": "whisper.cpp"}), encoding="utf-8")
        model = runtime / "transcription" / "models" / "ggml-tiny.bin"
        model.parent.mkdir(parents=True, exist_ok=True)
        model.write_bytes(b"model")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
            "release_channel": "development",
            "build_event": "push" if main_candidate else "pull_request",
            "build_ref": "refs/heads/main" if main_candidate else "refs/pull/81/merge",
            "physical_uat_candidate": bool(main_candidate),
            "signing_mode": "ad_hoc",
            "notarized": False,
        }), encoding="utf-8")
        self.runtime.repo_root = source
        return resources

    def test_source_checkout_is_not_misreported_as_physical_bundle_ready(self):
        with patch("binario_marketing.service_wave69_app.machine_snapshot", return_value=self._eligible_machine()):
            payload = self.runtime.physical_uat_preflight(self.company["id"])
        self.assertEqual(payload["schema"], "binario.marketing.physical-uat-preflight.v1")
        self.assertFalse(payload["ready_to_begin_physical_uat"])
        self.assertIn("certified-build-provenance", payload["blockers"])
        self.assertIn("main-candidate-build", payload["blockers"])
        self.assertIn("embedded-runtime", payload["blockers"])
        self.assertFalse(payload["physical_uat_complete"])
        self.assertFalse(payload["release_boundary"]["physical_preflight_is_release_authority"])

    def test_packaged_arm64_runtime_can_pass_preflight_without_completing_uat(self):
        self._fake_packaged_runtime()
        with patch("binario_marketing.service_wave69_app.machine_snapshot", return_value=self._eligible_machine()):
            payload = self.runtime.physical_uat_preflight(self.company["id"])
        self.assertTrue(payload["ready_to_begin_physical_uat"])
        self.assertEqual(payload["blockers"], [])
        self.assertTrue(all(row["passed"] for row in payload["checks"] if row["required"]))
        self.assertEqual(payload["next_action"]["code"], "START_PHYSICAL_UAT")
        self.assertGreaterEqual(payload["scenario_contract"]["required"], 5)
        self.assertTrue(payload["scenario_contract"]["manual_evidence_required"])
        self.assertFalse(payload["scenario_contract"]["automatic_pass"])
        self.assertFalse(payload["physical_uat_complete"])
        self.assertFalse(payload["release_boundary"]["release_ready"])
        self.assertFalse(payload["release_boundary"]["production_ready"])

    def test_pr_bundle_is_not_a_physical_uat_candidate_and_start_fails_closed(self):
        self._fake_packaged_runtime(main_candidate=False)
        machine = self._eligible_machine()
        with patch("binario_marketing.service_wave69_app.machine_snapshot", return_value=machine):
            payload = self.runtime.physical_uat_preflight(self.company["id"])
            self.assertFalse(payload["ready_to_begin_physical_uat"])
            self.assertIn("main-candidate-build", payload["blockers"])
            self.assertEqual(payload["next_action"]["code"], "RESOLVE_PREFLIGHT")
            with self.assertRaisesRegex(ValueError, "main-candidate-build"):
                self.runtime.start_physical_uat(self.company["id"], {"operator": "UAT"})
        self.assertEqual(self.runtime.physical_uat.list(self.company["id"]), [])

    def test_ci_is_ineligible_even_with_complete_packaged_runtime(self):
        self._fake_packaged_runtime()
        machine = dict(self._eligible_machine(), is_ci=True, physical_gate_eligible=False)
        with patch("binario_marketing.service_wave69_app.machine_snapshot", return_value=machine):
            payload = self.runtime.physical_uat_preflight(self.company["id"])
        self.assertFalse(payload["ready_to_begin_physical_uat"])
        self.assertEqual(payload["blockers"], ["physical-machine"])
        self.assertEqual(payload["next_action"]["code"], "RESOLVE_PREFLIGHT")

    def test_active_session_changes_next_action_but_preflight_records_no_result(self):
        self._fake_packaged_runtime()
        machine = self._eligible_machine()
        with patch("binario_marketing.service_wave69_app.machine_snapshot", return_value=machine), patch(
            "binario_marketing.physical_uat_store.machine_snapshot", return_value=machine
        ):
            session = self.runtime.start_physical_uat(self.company["id"], {"operator": "UAT"})
            payload = self.runtime.physical_uat_preflight(self.company["id"])
        self.assertEqual(payload["active_session_id"], session["id"])
        self.assertEqual(payload["next_action"]["code"], "CONTINUE_SESSION")
        self.assertFalse(payload["safety"]["physical_uat_result_recorded"])
        persisted = self.runtime.physical_uat.get(self.company["id"], session["id"])
        self.assertTrue(all(row["status"] == "PENDING" for row in persisted["scenarios"]))

    def test_http_serves_get_only_preflight_and_chains_ui_after_wave68(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/guided-physical-uat.js", timeout=5) as response:
                guided = response.read().decode("utf-8")
            self.assertIn("physical-uat-preflight.js", guided)
            self.assertIn("data-physical-uat-preflight-wave69", guided)
            with urlopen(base + "/physical-uat-preflight.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Preflight técnico del Mac y del bundle", ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/physical-uat/preflight", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], "binario.marketing.physical-uat-preflight.v1")
            self.assertFalse(payload["safety"]["marketing_mutation_performed"])
            self.assertFalse(payload["safety"]["provider_read_performed"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_browser_preflight_has_no_evidence_or_marketing_mutation_authority(self):
        ui = (ROOT / "web" / "physical-uat-preflight.js").read_text(encoding="utf-8")
        for marker in ("ready_to_begin_physical_uat", "PREFLIGHT BLOQUEADO", "LISTO PARA INICIAR", "Revalidar preflight"):
            self.assertIn(marker, ui)
        for forbidden in ("method:'POST'", "method:'PATCH'", "setInterval", "sendBeacon", "/opportunities", "/publications", "/paid-media", "/ai/generate", "supabase", "vercel"):
            self.assertNotIn(forbidden, ui.lower() if forbidden in {"supabase", "vercel"} else ui)

    def test_builder_keeps_w68_strict_then_injects_w69_and_release_remains_fail_closed(self):
        builder = (ROOT / "scripts" / "build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave68_app import serve", builder)
        self.assertIn("service_wave69_app import serve", builder)
        self.assertIn("audit_wave68_guided_physical_uat.sh", builder)
        self.assertIn("audit_wave69_physical_uat_preflight.sh", builder)
        self.assertLess(builder.index("audit_wave68_guided_physical_uat.sh"), builder.index("service_wave69_app import serve"))
        for wave in (59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69):
            self.assertIn(f"CURRENT ARM64 ITERATION BUILD PASS: Wave {wave}", builder)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        audit = (ROOT / "scripts" / "audit_wave69_physical_uat_preflight.sh").read_text(encoding="utf-8")
        self.assertIn("WAVE 69 PHYSICAL UAT PREFLIGHT AUDIT PASS", audit)


if __name__ == "__main__":
    unittest.main()
