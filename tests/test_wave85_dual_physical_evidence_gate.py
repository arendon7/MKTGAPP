from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave85DualPhysicalEvidenceGateTests(unittest.TestCase):
    def test_product_collector_binds_physical_session_to_exact_candidate(self):
        module = _load("wave85_product_collector", ROOT / "scripts/collect_product_uat.py")
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            app = root / "Binario Marketing IA.app"
            resources = app / "Contents/Resources"
            resources.mkdir(parents=True)
            candidate = {
                "schema": module.CANDIDATE_SCHEMA,
                "role": module.PHYSICAL_ROLE,
                "git_sha": "a" * 40,
                "architecture": "arm64",
                "product_version": "0.9.0.dev1",
                "runtime_wave": 76,
                "certification_guard_wave": 84,
                "candidate_source_sha256": "b" * 64,
                "build_origin": {"event": "push", "ref": "refs/heads/main", "trusted_for_physical_uat": True},
                "physical_uat": {"eligible_build_origin": True, "automatic_pass": False},
            }
            (resources / "PHYSICAL_UAT_CANDIDATE.json").write_text(json.dumps(candidate), encoding="utf-8")
            (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({"git_sha": "a" * 40, "architecture": "arm64", "product_version": "0.9.0.dev1"}), encoding="utf-8")
            session = {
                "schema": module.SESSION_SCHEMA,
                "id": "uat_" + "c" * 24,
                "company_id": "cmp_" + "d" * 24,
                "status": "PASSED",
                "machine": {"physical_gate_eligible": True, "is_ci": False},
                "build": {"git_sha": "a" * 40, "architecture": "arm64", "product_version": "0.9.0.dev1"},
                "scenarios": [{"id": "company-switch", "required": True, "status": "PASS"}],
                "physical_uat_complete": True,
                "evidence_sha256": None,
            }
            session["evidence_sha256"] = module._session_digest(session)
            session_path = root / "session.json"
            session_path.write_text(json.dumps(session), encoding="utf-8")
            report = module.collect(app, session_path)
            self.assertTrue(report["product_uat_passed"])
            self.assertEqual(report["git_sha"], "a" * 40)
            self.assertEqual(report["candidate_source_sha256"], "b" * 64)
            self.assertEqual(report["certification_guard_wave"], 85)
            self.assertFalse(report["release_authority"])
            session["scenarios"][0]["status"] = "FAIL"
            session_path.write_text(json.dumps(session), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "scenarios must PASS|digest mismatch"):
                module.collect(app, session_path)

    def test_release_gate_requires_both_phases_and_exact_binding(self):
        gate = _load("wave85_release_gate", ROOT / "scripts/release_candidate_gate.py")
        git_sha = "e" * 40
        source_sha = "f" * 64
        manifest_sha = "1" * 64
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            product = root / "product.json"
            release = root / "release.json"
            product.write_text(json.dumps({
                "schema": gate.PRODUCT_UAT_SCHEMA,
                "git_sha": git_sha,
                "architecture": "arm64",
                "product_version": "0.9.0.dev1",
                "runtime_wave": 76,
                "candidate_source_sha256": source_sha,
                "candidate_manifest_sha256": manifest_sha,
                "session_evidence_sha256": "2" * 64,
                "product_uat_passed": True,
                "release_authority": False,
                "production_ready": False,
            }), encoding="utf-8")
            release.write_text(json.dumps({
                "schema": gate.RELEASE_UAT_SCHEMA,
                "git_sha": git_sha,
                "architecture": "arm64",
                "runtime_wave": 76,
                "candidate_source_sha256": source_sha,
                "candidate_manifest_sha256": manifest_sha,
                "uat_passed": True,
                "overall": "UAT_PASS",
            }), encoding="utf-8")
            phase_a, _ = gate._product_uat_passed(product, git_sha=git_sha, architecture="arm64", product_version="0.9.0.dev1", candidate_source_sha256=source_sha, candidate_manifest_sha256=manifest_sha)
            phase_b, _ = gate._uat_passed(release, git_sha=git_sha, architecture="arm64", candidate_source_sha256=source_sha, candidate_manifest_sha256=manifest_sha)
            self.assertTrue(phase_a)
            self.assertTrue(phase_b)
            phase_a_missing, _ = gate._product_uat_passed(None, git_sha=git_sha, architecture="arm64", product_version="0.9.0.dev1", candidate_source_sha256=source_sha, candidate_manifest_sha256=manifest_sha)
            self.assertFalse(phase_a_missing)
            wrong, _ = gate._product_uat_passed(product, git_sha=git_sha, architecture="arm64", product_version="0.9.0.dev1", candidate_source_sha256="9" * 64, candidate_manifest_sha256=manifest_sha)
            self.assertFalse(wrong)

    def test_w85_is_certification_guard_not_runtime_or_release_opening(self):
        guard = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        pack = (ROOT / "scripts/package_current_arm64_candidate.py").read_text(encoding="utf-8")
        gate = (ROOT / "scripts/release_candidate_gate.py").read_text(encoding="utf-8")
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn("audit_wave85_dual_physical_evidence_gate.sh", guard)
        self.assertIn("CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 85", guard)
        self.assertIn("PRODUCT_UAT_COLLECT.py", pack)
        self.assertIn("COLLECT_PRODUCT_UAT.command", pack)
        self.assertIn('"dual_physical_uat_required": True', pack)
        for marker in ("physical_product_uat_missing_or_invalid", "release_operational_uat_missing_or_invalid", "dual_physical_uat_binding_mismatch", "dual_physical_uat_passed"):
            self.assertIn(marker, gate)
        self.assertIn("0.9.0.dev1", version)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        self.assertNotIn("service_wave85_app", guard)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
