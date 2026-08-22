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
    path = ROOT / "scripts/verify_physical_uat_handoff.py"
    spec = importlib.util.spec_from_file_location("wave84_verifier", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _sha256(module, path: Path) -> str:
    return module._sha256(path)


class Wave84PhysicalUATOperatorHandoffTests(unittest.TestCase):
    def test_operator_commands_are_shell_valid_and_never_auto_pass_uat(self):
        for name in ("start_physical_uat.command", "record_release_uat.command", "collect_product_uat.command"):
            path = ROOT / "scripts" / name
            subprocess.run(["bash", "-n", str(path)], check=True)
            source = path.read_text(encoding="utf-8")
            self.assertIn("arm64", source)
            self.assertNotIn("RELEASE_READY=True", source)
        start = (ROOT / "scripts/start_physical_uat.command").read_text(encoding="utf-8")
        self.assertIn("--require-physical-host", start)
        self.assertIn("collect_release_uat.py", start)

    def test_packager_and_verifier_remain_origin_aware_after_later_handoff_guard(self):
        package = (ROOT / "scripts/package_current_arm64_candidate.py").read_text(encoding="utf-8")
        verify = (ROOT / "scripts/verify_physical_uat_handoff.py").read_text(encoding="utf-8")
        self.assertIn('DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v3"', package)
        self.assertIn("EXPECTED_GUARD_WAVE = 84", package)
        self.assertIn("VALIDATION_BUILD_ONLY", package)
        self.assertIn("physical_uat_eligible", package)
        self.assertIn("VALIDATION_ROLE", verify)
        self.assertIn("physical UAT requires a trusted push build", verify)
        self.assertIn("refs/heads/main", verify)
        self.assertIn("refs/tags/v", verify)

    def _fixture(self, module, tmp: Path, git_sha: str, *, trusted: bool) -> tuple[Path, Path]:
        delivery_dir = tmp / "delivery"
        delivery_dir.mkdir()
        app = tmp / "Binario Marketing IA.app"
        resources = app / "Contents/Resources"
        resources.mkdir(parents=True)
        role = module.PHYSICAL_ROLE if trusted else module.VALIDATION_ROLE
        origin = {"event": "push" if trusted else "pull_request", "ref": "refs/heads/main" if trusted else "refs/pull/95/merge", "trusted_for_physical_uat": trusted}
        candidate = {
            "schema": module.CANDIDATE_SCHEMA,
            "role": role,
            "git_sha": git_sha,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
            "runtime_wave": 76,
            "certification_guard_wave": 84,
            "build_origin": origin,
            "candidate_source_sha256": "a" * 64,
            "release_boundary": {"release_ready": False, "release_tag": None, "production_ready": False},
            "physical_uat": {"required": True, "automatic_pass": False, "eligible_build_origin": trusted},
        }
        internal = resources / "PHYSICAL_UAT_CANDIDATE.json"
        external = delivery_dir / "PHYSICAL_UAT_CANDIDATE.json"
        payload = json.dumps(candidate, ensure_ascii=False, indent=2)
        internal.write_text(payload, encoding="utf-8")
        external.write_text(payload, encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({"schema": module.PROVENANCE_SCHEMA, "git_sha": git_sha, "architecture": "arm64", "product_version": "0.9.0.dev1"}), encoding="utf-8")
        (resources / "RELEASE_READINESS.json").write_text(json.dumps({"schema": module.READINESS_SCHEMA, "git_sha": git_sha, "architecture": "arm64"}), encoding="utf-8")
        artifact_name = f"Binario-Marketing-IA-PHYSICAL-UAT-arm64-{git_sha[:12]}.zip"
        artifact = delivery_dir / artifact_name
        artifact.write_bytes(b"exact-candidate-zip")
        artifact_sha = _sha256(module, artifact)
        (delivery_dir / f"{artifact_name}.sha256").write_text(f"{artifact_sha}  {artifact_name}\n", encoding="utf-8")
        helpers = {
            "PHYSICAL_UAT_HANDOFF_VERIFY.py": b"verify-helper",
            "START_PHYSICAL_UAT.command": b"start-helper",
            "RECORD_RELEASE_UAT.command": b"record-helper",
            "PRODUCT_UAT_COLLECT.py": b"product-collector",
            "COLLECT_PRODUCT_UAT.command": b"product-command",
            "PHYSICAL_UAT_OPERATOR.md": b"operator-guide",
        }
        for name, data in helpers.items():
            (delivery_dir / name).write_bytes(data)
        delivery = {
            "schema": module.DELIVERY_SCHEMA,
            "role": role,
            "build_origin": origin,
            "physical_uat_eligible": trusted,
            "git_sha": git_sha,
            "architecture": "arm64",
            "runtime_wave": 76,
            "certification_guard_wave": 84,
            "operator_handoff_wave": 85,
            "dual_evidence_guard_wave": 85,
            "candidate_source_sha256": "a" * 64,
            "candidate_manifest_sha256": _sha256(module, internal),
            "artifact": artifact_name,
            "artifact_sha256": artifact_sha,
            "handoff_verifier_sha256": _sha256(module, delivery_dir / "PHYSICAL_UAT_HANDOFF_VERIFY.py"),
            "start_command_sha256": _sha256(module, delivery_dir / "START_PHYSICAL_UAT.command"),
            "record_command_sha256": _sha256(module, delivery_dir / "RECORD_RELEASE_UAT.command"),
            "product_uat_collector_sha256": _sha256(module, delivery_dir / "PRODUCT_UAT_COLLECT.py"),
            "product_uat_command_sha256": _sha256(module, delivery_dir / "COLLECT_PRODUCT_UAT.command"),
            "operator_guide_sha256": _sha256(module, delivery_dir / "PHYSICAL_UAT_OPERATOR.md"),
            "physical_uat_required": True,
            "physical_product_uat_required": True,
            "release_operational_uat_required": True,
            "dual_physical_uat_required": True,
            "automatic_uat_pass": False,
            "release_ready": False,
            "release_tag": None,
            "production_ready": False,
        }
        (delivery_dir / "FULL_MAC_DELIVERY.json").write_text(json.dumps(delivery), encoding="utf-8")
        return delivery_dir, app

    def test_integrity_verification_accepts_validation_and_physical_roles(self):
        module = _load_verifier()
        git_sha = "b" * 40
        for trusted in (False, True):
            with self.subTest(trusted=trusted), tempfile.TemporaryDirectory() as tmpdir:
                delivery_dir, app = self._fixture(module, Path(tmpdir), git_sha, trusted=trusted)
                report = module.verify(delivery_dir, app, expected_git_sha=git_sha)
                self.assertIs(report["physical_uat_eligible"], trusted)
                self.assertEqual(report["role"], module.PHYSICAL_ROLE if trusted else module.VALIDATION_ROLE)
                self.assertFalse(report["automatic_uat_pass"])

    def test_physical_start_rejects_validation_even_on_real_arm64_shape(self):
        module = _load_verifier()
        git_sha = "c" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            delivery_dir, app = self._fixture(module, Path(tmpdir), git_sha, trusted=False)
            with patch.object(module.platform, "system", return_value="Darwin"), patch.object(module.platform, "machine", return_value="arm64"), patch.dict(module.os.environ, {"CI": "", "GITHUB_ACTIONS": ""}, clear=False):
                with self.assertRaisesRegex(ValueError, "trusted push build"):
                    module.verify(delivery_dir, app, expected_git_sha=git_sha, require_physical_host=True)

    def test_physical_start_accepts_trusted_candidate_on_real_arm64_shape(self):
        module = _load_verifier()
        git_sha = "d" * 40
        with tempfile.TemporaryDirectory() as tmpdir:
            delivery_dir, app = self._fixture(module, Path(tmpdir), git_sha, trusted=True)
            with patch.object(module.platform, "system", return_value="Darwin"), patch.object(module.platform, "machine", return_value="arm64"), patch.dict(module.os.environ, {"CI": "", "GITHUB_ACTIONS": ""}, clear=False):
                report = module.verify(delivery_dir, app, expected_git_sha=git_sha, require_physical_host=True)
                self.assertTrue(report["ready_for_operator_uat"])


if __name__ == "__main__":
    unittest.main()
