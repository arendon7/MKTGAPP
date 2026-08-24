from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts" / "verify_combined_uat_attestation.py"
GATE_PATH = ROOT / "scripts" / "release_candidate_gate.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "persistent-release.yml"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _attestation(*, git_sha: str, source_sha: str, manifest_sha: str = "b" * 64) -> dict:
    core = {
        "schema": "binario.marketing.combined-physical-uat-attestation.v1",
        "binding": {
            "git_sha": git_sha,
            "product_version": "0.9.0.dev1",
            "architecture": "arm64",
            "runtime_wave": 76,
            "certification_guard_wave": 84,
            "candidate_source_sha256": source_sha,
            "candidate_manifest_sha256": manifest_sha,
            "build_origin": {"event": "push", "ref": "refs/heads/main", "trusted_for_physical_uat": True},
            "provenance_schema": "binario.marketing.full-mac-build.v4",
        },
        "phase_a": {
            "session_id": "session-1",
            "evidence_sha256": "c" * 64,
            "required_scenarios": 5,
            "passed_scenarios": 5,
            "finished_at": "2026-08-22T12:00:00+00:00",
            "report_sha256": "d" * 64,
        },
        "phase_b": {
            "required_gates": 12,
            "passed_gates": 12,
            "overall": "UAT_PASS",
            "updated_at": "2026-08-22T12:05:00+00:00",
            "report_sha256": "e" * 64,
        },
        "both_phases_passed": True,
        "release_authority": False,
        "production_ready": False,
    }
    return {**core, "generated_at": "2026-08-22T12:06:00+00:00", "attestation_sha256": _digest(core)}


class Wave86SafeUATEvidenceTransportTests(unittest.TestCase):
    def test_attestation_verifier_binds_exact_release_sha_and_detects_tamper(self):
        verify = _module(VERIFY_PATH, "wave86_verify")
        git_sha = "a" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "combined.json"
            row = _attestation(git_sha=git_sha, source_sha="f" * 64)
            path.write_text(json.dumps(row), encoding="utf-8")
            report = verify.verify(path, expected_git_sha=git_sha)
            self.assertTrue(report["both_phases_passed"])
            self.assertFalse(report["release_authority"])
            with self.assertRaisesRegex(ValueError, "git SHA mismatch"):
                verify.verify(path, expected_git_sha="9" * 40)
            row["phase_b"]["passed_gates"] = 11
            path.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify.verify(path, expected_git_sha=git_sha)

    def test_gate_accepts_arm64_attestation_for_source_equivalent_x86_without_physical_x86_claim(self):
        gate = _module(GATE_PATH, "wave86_gate")
        git_sha = "1" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            for name in ("src", "web", "apps"):
                root = source / name
                root.mkdir(parents=True)
                (root / "fixture.txt").write_text(f"{name}-same-source", encoding="utf-8")
            source_sha = gate._source_digest(source)
            evidence = Path(tmpdir) / "combined.json"
            evidence.write_text(json.dumps(_attestation(git_sha=git_sha, source_sha=source_sha)), encoding="utf-8")
            passed, row, mode = gate._uat_passed(
                evidence,
                git_sha=git_sha,
                architecture="x86_64",
                product_version="0.9.0.dev1",
                current_source_sha256=source_sha,
                candidate_source_sha256=None,
                candidate_manifest_sha256=None,
            )
            self.assertTrue(passed)
            self.assertEqual(mode, "source_equivalent_cross_arch_distribution")
            self.assertEqual((row or {}).get("binding", {}).get("architecture"), "arm64")

    def test_gate_rejects_cross_arch_when_source_digest_differs(self):
        gate = _module(GATE_PATH, "wave86_gate_mismatch")
        git_sha = "2" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = Path(tmpdir) / "combined.json"
            evidence.write_text(json.dumps(_attestation(git_sha=git_sha, source_sha="a" * 64)), encoding="utf-8")
            passed, _, mode = gate._uat_passed(
                evidence,
                git_sha=git_sha,
                architecture="x86_64",
                product_version="0.9.0.dev1",
                current_source_sha256="b" * 64,
                candidate_source_sha256=None,
                candidate_manifest_sha256=None,
            )
            self.assertFalse(passed)
            self.assertIsNone(mode)

    def test_arm64_tag_rebuild_is_source_equivalent_not_exact_when_manifest_changes(self):
        gate = _module(GATE_PATH, "wave86_gate_arm64")
        git_sha = "3" * 40
        source_sha = "c" * 64
        with tempfile.TemporaryDirectory() as tmpdir:
            evidence = Path(tmpdir) / "combined.json"
            evidence.write_text(json.dumps(_attestation(git_sha=git_sha, source_sha=source_sha, manifest_sha="4" * 64)), encoding="utf-8")
            passed, _, mode = gate._uat_passed(
                evidence,
                git_sha=git_sha,
                architecture="arm64",
                product_version="0.9.0.dev1",
                current_source_sha256=source_sha,
                candidate_source_sha256=source_sha,
                candidate_manifest_sha256="5" * 64,
            )
            self.assertTrue(passed)
            self.assertEqual(mode, "source_equivalent_arm64_rebuild")

    def test_persistent_release_transports_verified_attestation_before_packaging(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("PHYSICAL_UAT_ATTESTATION_B64", workflow)
        self.assertIn("verify_combined_uat_attestation.py", workflow)
        self.assertIn("verified-physical-uat-attestation-${{ github.sha }}", workflow)
        self.assertIn("actions/upload-artifact@v4", workflow)
        self.assertIn("actions/download-artifact@v4", workflow)
        gate = workflow.index("release_candidate_gate.py")
        package = workflow.index("Package immutable release asset")
        self.assertLess(gate, package)
        window = workflow[gate:package]
        self.assertIn("--production", window)
        self.assertIn("--uat-evidence", window)
        self.assertIn("combined-physical-uat-attestation.json", window)

    def test_release_boundary_and_workflow_count_remain_non_authoritative(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
