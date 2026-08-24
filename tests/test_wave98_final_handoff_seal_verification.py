from __future__ import annotations

import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_COMBINED = ROOT / "scripts/verify_combined_uat_attestation.py"
VERIFY_HANDOFF = ROOT / "scripts/verify_physical_uat_handoff.py"
FINALIZE_COMMAND = ROOT / "scripts/finalize_physical_uat.command"
VERSION = ROOT / "src/binario_marketing/version.py"


def _module():
    spec = importlib.util.spec_from_file_location("wave98_combined_verify", VERIFY_COMBINED)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave98FinalHandoffSealVerificationTests(unittest.TestCase):
    def test_w98_reconstructs_exact_handoff_verifier_cli_bytes(self):
        module = _module()
        payload = {
            "schema": module.W97_HANDOFF_SCHEMA,
            "git_sha": "a" * 40,
            "host": {"system": "Darwin", "machine": "arm64", "is_ci": False},
            "candidate_source_sha256": "b" * 64,
        }
        expected_bytes = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        expected_sha = hashlib.sha256(expected_bytes).hexdigest()
        self.assertEqual(module._handoff_report_sha256(payload), expected_sha)

        handoff_source = VERIFY_HANDOFF.read_text(encoding="utf-8")
        self.assertIn("json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)", handoff_source)
        finalizer_source = FINALIZE_COMMAND.read_text(encoding="utf-8")
        self.assertIn('"handoff_verification_sha256": file_sha(verify_path)', finalizer_source)

    def test_w98_requires_declared_handoff_sha_to_match_embedded_handoff_bytes(self):
        source = VERIFY_COMBINED.read_text(encoding="utf-8")
        self.assertIn("_handoff_report_sha256(handoff) == handoff_sha", source)
        self.assertIn("W97 final handoff verification SHA-256 mismatch", source)
        self.assertIn('"w98_handoff_seal_verified"', source)

    def test_w98_does_not_mutate_release_identity_runtime_or_workflow_count(self):
        version = VERSION.read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        source = VERIFY_COMBINED.read_text(encoding="utf-8")
        self.assertIn("EXPECTED_RUNTIME_WAVE = 76", source)
        self.assertNotIn("gh release create", source)
        self.assertNotIn("RELEASE_READY = True", source)


if __name__ == "__main__":
    unittest.main()
