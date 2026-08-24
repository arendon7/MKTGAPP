from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FINALIZER_PATH = ROOT / "scripts/finalize_physical_uat.py"


def _module():
    spec = importlib.util.spec_from_file_location("wave85_finalizer", FINALIZER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave85CombinedPhysicalUATAttestationTests(unittest.TestCase):
    def _fixture(self, module, tmp: Path, *, trusted: bool = True):
        git_sha = "a" * 40
        app = tmp / "Binario Marketing IA.app"
        resources = app / "Contents/Resources"
        resources.mkdir(parents=True)
        origin = {
            "event": "push" if trusted else "pull_request",
            "ref": "refs/heads/main" if trusted else "refs/pull/95/merge",
            "trusted_for_physical_uat": trusted,
        }
        candidate = {
            "schema": module.CANDIDATE_SCHEMA,
            "role": module.EXPECTED_ROLE if trusted else "VALIDATION_BUILD_ONLY",
            "git_sha": git_sha,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
            "runtime_wave": 76,
            "certification_guard_wave": 84,
            "source_contract_wave": 95,
            "source_release_state": "LOCKED_SOURCE",
            "build_origin": origin,
            "candidate_source_sha256": "b" * 64,
            "release_boundary": {
                "source_release_state": "LOCKED_SOURCE",
                "release_ready": False,
                "release_tag": None,
                "operational_authorization": False,
                "release_authority": False,
                "publication_authority": False,
                "production_ready": False,
            },
            "physical_uat": {"required": True, "automatic_pass": False, "eligible_build_origin": trusted},
        }
        candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({
            "schema": "binario.marketing.full-mac-build.v4",
            "git_sha": git_sha,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
        }), encoding="utf-8")

        session = {
            "schema": "binario.marketing.physical-uat-session.v1",
            "id": "uat_" + "1" * 24,
            "company_id": "cmp_" + "2" * 24,
            "status": "PASSED",
            "operator": "QA",
            "notes": None,
            "created_at": "2026-08-22T00:00:00+00:00",
            "updated_at": "2026-08-22T00:10:00+00:00",
            "finished_at": "2026-08-22T00:10:00+00:00",
            "machine": {"system": "Darwin", "machine": "arm64", "is_ci": False, "physical_gate_eligible": True},
            "build": {"source": "BUILD_PROVENANCE.json", "git_sha": git_sha, "architecture": "arm64", "product_version": "0.9.0.dev1"},
            "scenarios": [
                {"id": scenario, "required": True, "status": "PASS", "note": "observed", "updated_at": "2026-08-22T00:05:00+00:00"}
                for scenario in ("company-switch", "inbox-to-crm", "pipeline-followup", "campaign-execution", "results-decision")
            ] + [{"id": "optional-ai", "required": False, "status": "SKIPPED", "note": None, "updated_at": "2026-08-22T00:06:00+00:00"}],
            "readiness_at_finish": {},
            "evidence_sha256": None,
            "physical_uat_complete": True,
        }
        session["evidence_sha256"] = module._digest({**session, "evidence_sha256": None})
        phase_a = {
            "schema": module.PHASE_A_SCHEMA,
            "session": session,
            "summary": {"required": 5, "passed": 5, "failed": 0, "blocked": 0, "pending": 0, "physical_gate_eligible": True, "physical_uat_complete": True},
            "release_authority": False,
        }
        phase_a_path = tmp / "phase-a.json"
        phase_a_path.write_text(json.dumps(phase_a), encoding="utf-8")

        manual = [{
            "id": gate,
            "status": "PASS",
            "step": gate,
            "note": f"Observed {gate} on exact candidate",
            "recorded_at": "2026-08-22T00:20:00+00:00",
        } for gate in sorted(module.REQUIRED_PHASE_B_IDS)]
        phase_b = {
            "schema": module.PHASE_B_SCHEMA,
            "git_sha": git_sha,
            "architecture": "arm64",
            "version": "0.9.0.dev1",
            "runtime_wave": 76,
            "source_contract_wave": 95,
            "source_release_state": "LOCKED_SOURCE",
            "source_release_tag": None,
            "candidate_source_sha256": "b" * 64,
            "candidate_manifest_sha256": module._sha256_file(candidate_path),
            "automatic_passed": True,
            "manual_steps": manual,
            "uat_passed": True,
            "overall": "UAT_PASS",
            "release_authority": False,
            "publication_authority": False,
            "production_ready": False,
            "updated_at": "2026-08-22T00:20:00+00:00",
        }
        phase_b_path = tmp / "phase-b.json"
        phase_b_path.write_text(json.dumps(phase_b), encoding="utf-8")
        return app, phase_a_path, phase_b_path

    def test_combines_both_phases_without_release_authority_or_raw_notes(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            app, phase_a, phase_b = self._fixture(module, Path(tmpdir))
            report = module.finalize(app, phase_a, phase_b)
            self.assertTrue(report["both_phases_passed"])
            self.assertFalse(report["release_authority"])
            self.assertFalse(report["publication_authority"])
            self.assertFalse(report["production_ready"])
            self.assertEqual(report["binding"]["runtime_wave"], 76)
            self.assertEqual(report["binding"]["attestation_wave"], 85)
            self.assertEqual(report["binding"]["source_contract_wave"], 95)
            self.assertEqual(report["binding"]["source_release_state"], "LOCKED_SOURCE")
            self.assertEqual(report["phase_a"]["passed_scenarios"], 5)
            self.assertEqual(report["phase_b"]["passed_gates"], 12)
            encoded = json.dumps(report, ensure_ascii=False)
            self.assertNotIn("Observed credentials", encoded)
            self.assertEqual(len(report["attestation_sha256"]), 64)

    def test_rejects_validation_only_candidate(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            app, phase_a, phase_b = self._fixture(module, Path(tmpdir), trusted=False)
            with self.assertRaisesRegex(ValueError, "not physical-UAT eligible"):
                module.finalize(app, phase_a, phase_b)

    def test_rejects_phase_a_digest_tampering(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            app, phase_a, phase_b = self._fixture(module, Path(tmpdir))
            data = json.loads(phase_a.read_text(encoding="utf-8")); data["session"]["evidence_sha256"] = "0" * 64; phase_a.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Phase A session evidence digest mismatch"):
                module.finalize(app, phase_a, phase_b)

    def test_rejects_phase_b_without_concrete_manual_note(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            app, phase_a, phase_b = self._fixture(module, Path(tmpdir))
            data = json.loads(phase_b.read_text(encoding="utf-8")); data["manual_steps"][0]["note"] = ""; phase_b.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "lacks concrete note"):
                module.finalize(app, phase_a, phase_b)

    def test_operator_export_and_finalization_are_explicit(self):
        ui = (ROOT / "web/release-evidence.js").read_text(encoding="utf-8")
        self.assertIn("Descargar evidencia Fase A", ui)
        self.assertIn("/physical-uat/${encodeURIComponent(sessionId)}/report", ui)
        command = ROOT / "scripts/finalize_physical_uat.command"
        subprocess.run(["bash", "-n", str(command)], check=True)
        source = command.read_text(encoding="utf-8")
        self.assertIn("FINALIZE_PHYSICAL_UAT.py", source)
        self.assertIn("release-uat-evidence.json", source)
        self.assertNotIn("RELEASE_READY=True", source)

    def test_packager_binds_combined_finalization_helpers(self):
        source = (ROOT / "scripts/package_current_arm64_candidate.py").read_text(encoding="utf-8")
        self.assertIn("COMBINED_ATTESTATION_WAVE = 85", source)
        self.assertIn("SOURCE_CONTRACT_WAVE = 95", source)
        self.assertIn("combined_finalizer_sha256", source)
        self.assertIn("finalize_command_sha256", source)
        self.assertIn("combined_attestation_required_before_release_transport", source)
        verifier = (ROOT / "scripts/verify_physical_uat_handoff.py").read_text(encoding="utf-8")
        self.assertIn("FINALIZE_PHYSICAL_UAT.py", verifier)
        self.assertIn("SOURCE_CONTRACT_WAVE = 95", verifier)
        self.assertIn("combined attestation release-transport boundary missing", verifier)

    def test_prepared_source_stays_fail_closed_as_w86_supersedes_transport_hard_stop(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflow = (ROOT / ".github/workflows/persistent-release.yml").read_text(encoding="utf-8")
        self.assertIn("PHYSICAL_UAT_ATTESTATION_B64", workflow)
        self.assertIn("verify_combined_uat_attestation.py", workflow)
        self.assertIn("--expected-source-release-state PREPARED_RELEASE", workflow)
        self.assertIn("release_candidate_gate.py", workflow)
        gate = workflow.index("release_candidate_gate.py")
        package = workflow.index("Package immutable release asset")
        self.assertLess(gate, package)
        self.assertIn("--production", workflow[gate:package])
        self.assertIn("--uat-evidence", workflow[gate:package])
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
