from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _load_verifier():
    path = ROOT / "scripts" / "verify_physical_uat_handoff.py"
    spec = importlib.util.spec_from_file_location("wave84_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(module, path: Path) -> str:
    return module._sha256(path)


class Wave84PhysicalUATOperatorHandoffTests(unittest.TestCase):
    def test_operator_commands_are_shell_valid_and_never_auto_pass_uat(self):
        for name in ("start_physical_uat.command", "record_release_uat.command"):
            path = ROOT / "scripts" / name
            subprocess.run(["bash", "-n", str(path)], check=True)
            source = path.read_text(encoding="utf-8")
            self.assertIn("arm64", source)
            self.assertIn("GITHUB_ACTIONS", source)
            self.assertNotIn("RELEASE_READY=True", source)
        start = (ROOT / "scripts/start_physical_uat.command").read_text(encoding="utf-8")
        self.assertIn("collect_release_uat.py", start)
        self.assertIn("company-switch", start)
        self.assertIn("results-decision", start)
        record = (ROOT / "scripts/record_release_uat.command").read_text(encoding="utf-8")
        self.assertIn("record_release_uat.py", record)
        self.assertIn("concrete evidence note", record)

    def test_full_mac_artifact_uploads_complete_operator_handoff(self):
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertIn("- name: Package and hash", workflow)
        self.assertIn("PHYSICAL_UAT_HANDOFF_VERIFY.py", workflow)
        self.assertIn("START_PHYSICAL_UAT.command", workflow)
        self.assertIn("RECORD_RELEASE_UAT.command", workflow)
        self.assertIn("PHYSICAL_UAT_OPERATOR.md", workflow)
        self.assertIn("binario-marketing-physical-uat-candidate-arm64", workflow)

    def test_packager_binds_dual_uat_handoff_helpers_without_release_authority(self):
        source = (ROOT / "scripts/package_current_arm64_candidate.py").read_text(encoding="utf-8")
        self.assertIn("OPERATOR_HANDOFF_WAVE = 84", source)
        self.assertIn('"physical_product_uat_required": True', source)
        self.assertIn('"release_operational_uat_required": True', source)
        self.assertIn('"handoff_verifier_sha256"', source)
        self.assertIn('"start_command_sha256"', source)
        self.assertIn('"record_command_sha256"', source)
        self.assertIn('"operator_guide_sha256"', source)
        self.assertIn("starter_path.chmod(0o755)", source)
        self.assertIn("recorder_path.chmod(0o755)", source)
        self.assertIn('"release_ready": False', source)
        self.assertIn('"production_ready": False', source)

    def _fixture(self, module, tmp: Path, git_sha: str) -> tuple[Path, Path]:
        delivery_dir = tmp / "delivery"
        delivery_dir.mkdir()
        app = tmp / "Binario Marketing IA.app"
        resources = app / "Contents" / "Resources"
        resources.mkdir(parents=True)

        candidate = {
            "schema": module.CANDIDATE_SCHEMA,
            "role": module.EXPECTED_ROLE,
            "git_sha": git_sha,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
            "runtime_wave": 76,
            "certification_guard_wave": 81,
            "candidate_source_sha256": "a" * 64,
            "release_boundary": {"release_ready": False, "release_tag": None, "production_ready": False},
            "physical_uat": {"required": True, "automatic_pass": False},
        }
        internal = resources / "PHYSICAL_UAT_CANDIDATE.json"
        external = delivery_dir / "PHYSICAL_UAT_CANDIDATE.json"
        payload = json.dumps(candidate, ensure_ascii=False, indent=2)
        internal.write_text(payload, encoding="utf-8")
        external.write_text(payload, encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({
            "schema": module.PROVENANCE_SCHEMA,
            "git_sha": git_sha,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
        }), encoding="utf-8")
        (resources / "RELEASE_READINESS.json").write_text(json.dumps({
            "schema": module.READINESS_SCHEMA,
            "git_sha": git_sha,
            "architecture": "arm64",
        }), encoding="utf-8")

        artifact_name = f"Binario-Marketing-IA-PHYSICAL-UAT-arm64-{git_sha[:12]}.zip"
        artifact = delivery_dir / artifact_name
        artifact.write_bytes(b"exact-candidate-zip")
        artifact_sha = _sha256(module, artifact)
        (delivery_dir / f"{artifact_name}.sha256").write_text(f"{artifact_sha}  {artifact_name}\n", encoding="utf-8")

        helpers = {
            "PHYSICAL_UAT_HANDOFF_VERIFY.py": b"verify-helper",
            "START_PHYSICAL_UAT.command": b"start-helper",
            "RECORD_RELEASE_UAT.command": b"record-helper",
            "PHYSICAL_UAT_OPERATOR.md": b"operator-guide",
        }
        for name, data in helpers.items():
            (delivery_dir / name).write_bytes(data)

        delivery = {
            "schema": module.DELIVERY_SCHEMA,
            "role": module.EXPECTED_ROLE,
            "git_sha": git_sha,
            "architecture": "arm64",
            "runtime_wave": 76,
            "certification_guard_wave": 81,
            "operator_handoff_wave": 84,
            "candidate_source_sha256": "a" * 64,
            "candidate_manifest_sha256": _sha256(module, internal),
            "artifact": artifact_name,
            "artifact_sha256": artifact_sha,
            "handoff_verifier_sha256": _sha256(module, delivery_dir / "PHYSICAL_UAT_HANDOFF_VERIFY.py"),
            "start_command_sha256": _sha256(module, delivery_dir / "START_PHYSICAL_UAT.command"),
            "record_command_sha256": _sha256(module, delivery_dir / "RECORD_RELEASE_UAT.command"),
            "operator_guide_sha256": _sha256(module, delivery_dir / "PHYSICAL_UAT_OPERATOR.md"),
            "physical_uat_required": True,
            "physical_product_uat_required": True,
            "release_operational_uat_required": True,
            "automatic_uat_pass": False,
            "release_ready": False,
            "release_tag": None,
            "production_ready": False,
        }
        (delivery_dir / "FULL_MAC_DELIVERY.json").write_text(json.dumps(delivery), encoding="utf-8")
        return delivery_dir, app

    def test_verifier_accepts_exact_dual_gate_handoff_and_rejects_helper_tamper(self):
        module = _load_verifier()
        git_sha = "b" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            delivery_dir, app = self._fixture(module, Path(tmpdir), git_sha)
            report = module.verify(delivery_dir, app, expected_git_sha=git_sha)
            self.assertEqual(report["operator_handoff_wave"], 84)
            self.assertTrue(report["physical_product_uat_required"])
            self.assertTrue(report["release_operational_uat_required"])
            self.assertFalse(report["automatic_uat_pass"])
            self.assertFalse(report["release_authority"])
            (delivery_dir / "START_PHYSICAL_UAT.command").write_text("tampered", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "helper digest mismatch"):
                module.verify(delivery_dir, app, expected_git_sha=git_sha)

    def test_physical_host_requirement_fails_closed_outside_real_arm64_mac(self):
        module = _load_verifier()
        git_sha = "c" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            delivery_dir, app = self._fixture(module, Path(tmpdir), git_sha)
            with patch.object(module.platform, "system", return_value="Linux"), patch.object(module.platform, "machine", return_value="x86_64"):
                with self.assertRaisesRegex(ValueError, "real non-CI Darwin arm64 host"):
                    module.verify(delivery_dir, app, expected_git_sha=git_sha, require_physical_host=True)


if __name__ == "__main__":
    unittest.main()
