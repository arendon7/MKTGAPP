from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_packager():
    path = ROOT / "scripts/package_current_arm64_candidate.py"
    spec = importlib.util.spec_from_file_location("wave83_packager", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave83CurrentArm64CandidateArtifactTests(unittest.TestCase):
    def test_workflow_uses_current_guarded_builder_and_current_candidate_identity(self):
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/build_full_mac_current_guarded.sh --arch arm64", workflow)
        self.assertIn("package_current_arm64_candidate.py", workflow)
        self.assertIn("binario-marketing-physical-uat-candidate-arm64", workflow)
        self.assertIn("Binario-Marketing-IA-PHYSICAL-UAT-arm64-*.zip", workflow)
        self.assertNotIn("binario-marketing-wave47-arm64", workflow)

    def test_external_delivery_keeps_wave83_exact_identity_with_later_guards(self):
        source = (ROOT / "scripts/package_current_arm64_candidate.py").read_text(encoding="utf-8")
        self.assertIn('DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v3"', source)
        self.assertIn("EXPECTED_RUNTIME_WAVE = 76", source)
        self.assertIn("EXPECTED_GUARD_WAVE = 84", source)
        self.assertIn("SOURCE_CONTRACT_WAVE = 94", source)
        for marker in (
            "candidate_source_sha256",
            "candidate_manifest_sha256",
            "artifact_sha256",
            "physical_uat_required",
            "automatic_uat_pass",
            "operational_authorization",
            "release_authority",
            "publication_authority",
            "production_ready",
        ):
            self.assertIn(marker, source)
        self.assertIn("physical_uat_eligible", source)
        self.assertIn("VALIDATION_BUILD_ONLY", source)
        self.assertIn("LOCKED_SOURCE", source)
        self.assertIn("PREPARED_RELEASE", source)

    @staticmethod
    def _manifest(module, git_sha: str, *, trusted: bool) -> dict:
        return {
            "schema": module.CANDIDATE_SCHEMA,
            "role": module.PHYSICAL_ROLE if trusted else module.VALIDATION_ROLE,
            "git_sha": git_sha,
            "architecture": "arm64",
            "product": "BINARIO Marketing IA",
            "product_version": "0.9.0.dev1",
            "runtime_wave": 76,
            "certification_guard_wave": 84,
            "source_contract_wave": 94,
            "source_release_state": "LOCKED_SOURCE",
            "candidate_source_sha256": "e" * 64,
            "build_origin": {
                "event": "push" if trusted else "pull_request",
                "ref": "refs/heads/main" if trusted else "refs/pull/96/merge",
                "trusted_for_physical_uat": trusted,
            },
            "release_boundary": {
                "source_release_state": "LOCKED_SOURCE",
                "release_ready": False,
                "release_tag": None,
                "operational_authorization": False,
                "release_authority": False,
                "publication_authority": False,
                "production_ready": False,
            },
            "physical_uat": {
                "required": True,
                "automatic_pass": False,
                "eligible_build_origin": trusted,
            },
        }

    def test_candidate_validation_rejects_stale_git_sha(self):
        module = _load_packager(); expected = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Binario Marketing IA.app"
            resources = app / "Contents/Resources"
            resources.mkdir(parents=True)
            (resources / "PHYSICAL_UAT_CANDIDATE.json").write_text(
                json.dumps(self._manifest(module, "b" * 40, trusted=True)), encoding="utf-8"
            )
            with self.assertRaisesRegex(ValueError, "candidate git SHA mismatch"):
                module._validate_candidate(app, expected)

    def test_candidate_validation_accepts_exact_physical_and_validation_roles(self):
        module = _load_packager(); expected = "d" * 40
        for trusted in (True, False):
            with self.subTest(trusted=trusted), tempfile.TemporaryDirectory() as tmp:
                app = Path(tmp) / "Binario Marketing IA.app"
                resources = app / "Contents/Resources"
                resources.mkdir(parents=True)
                path = resources / "PHYSICAL_UAT_CANDIDATE.json"
                path.write_text(json.dumps(self._manifest(module, expected, trusted=trusted)), encoding="utf-8")
                manifest_path, actual, actual_trusted, source_state, source_tag = module._validate_candidate(app, expected)
                self.assertEqual(manifest_path, path)
                self.assertEqual(actual["git_sha"], expected)
                self.assertIs(actual_trusted, trusted)
                self.assertEqual(source_state, "LOCKED_SOURCE")
                self.assertIsNone(source_tag)


if __name__ == "__main__":
    unittest.main()
