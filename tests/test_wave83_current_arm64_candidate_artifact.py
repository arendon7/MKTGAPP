from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_packager():
    path = ROOT / "scripts" / "package_current_arm64_candidate.py"
    spec = importlib.util.spec_from_file_location("wave83_packager", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave83CurrentArm64CandidateArtifactTests(unittest.TestCase):
    def test_workflow_uses_current_guarded_builder_and_current_candidate_identity(self):
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertIn("scripts/build_full_mac_current_guarded.sh --arch arm64", workflow)
        self.assertNotIn("scripts/build_full_mac_wave47.sh --arch arm64", workflow)
        self.assertIn("package_current_arm64_candidate.py", workflow)
        self.assertIn("binario-marketing-physical-uat-candidate-arm64", workflow)
        self.assertIn("Binario-Marketing-IA-PHYSICAL-UAT-arm64-*.zip", workflow)
        self.assertNotIn("Binario-Marketing-IA-W47-arm64-", workflow)
        self.assertNotIn("binario-marketing-wave47-arm64", workflow)
        self.assertNotIn('"wave":47', workflow)

    def test_external_delivery_metadata_is_bound_to_wave81_candidate_truth(self):
        source = (ROOT / "scripts/package_current_arm64_candidate.py").read_text(encoding="utf-8")
        self.assertIn('DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v2"', source)
        self.assertIn("EXPECTED_RUNTIME_WAVE = 76", source)
        self.assertIn("EXPECTED_GUARD_WAVE = 81", source)
        self.assertIn('"candidate_source_sha256"', source)
        self.assertIn('"candidate_manifest_sha256"', source)
        self.assertIn('"artifact_sha256"', source)
        self.assertIn('"physical_uat_required": True', source)
        self.assertIn('"automatic_uat_pass": False', source)
        self.assertIn('"release_ready": False', source)
        self.assertIn('"production_ready": False', source)

    def test_candidate_validation_rejects_stale_git_sha(self):
        module = _load_packager()
        expected = "a" * 40
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Binario Marketing IA.app"
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True)
            manifest = {
                "schema": module.CANDIDATE_SCHEMA,
                "role": module.EXPECTED_ROLE,
                "git_sha": "b" * 40,
                "architecture": "arm64",
                "product_version": "0.9.0.dev1",
                "runtime_wave": 76,
                "certification_guard_wave": 81,
                "candidate_source_sha256": "c" * 64,
                "release_boundary": {
                    "release_ready": False,
                    "release_tag": None,
                    "production_ready": False,
                },
                "physical_uat": {"required": True, "automatic_pass": False},
            }
            (resources / "PHYSICAL_UAT_CANDIDATE.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "candidate git SHA mismatch"):
                module._validate_candidate(app, expected)

    def test_candidate_validation_accepts_exact_fail_closed_manifest(self):
        module = _load_packager()
        expected = "d" * 40
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Binario Marketing IA.app"
            resources = app / "Contents" / "Resources"
            resources.mkdir(parents=True)
            manifest = {
                "schema": module.CANDIDATE_SCHEMA,
                "role": module.EXPECTED_ROLE,
                "git_sha": expected,
                "architecture": "arm64",
                "product": "BINARIO Marketing IA",
                "product_version": "0.9.0.dev1",
                "runtime_wave": 76,
                "certification_guard_wave": 81,
                "candidate_source_sha256": "e" * 64,
                "release_boundary": {
                    "release_ready": False,
                    "release_tag": None,
                    "production_ready": False,
                },
                "physical_uat": {"required": True, "automatic_pass": False},
            }
            path = resources / "PHYSICAL_UAT_CANDIDATE.json"
            path.write_text(json.dumps(manifest), encoding="utf-8")
            manifest_path, actual = module._validate_candidate(app, expected)
            self.assertEqual(manifest_path, path)
            self.assertEqual(actual["git_sha"], expected)


if __name__ == "__main__":
    unittest.main()
