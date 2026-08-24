from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY = ROOT / "scripts/verify_combined_uat_attestation.py"
FINALIZE_COMMAND = ROOT / "scripts/finalize_physical_uat.command"


def _module():
    spec = importlib.util.spec_from_file_location("w97_combined_verify", VERIFY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepared_attestation(module, *, include_w97: bool = True, extracted_source_sha: str | None = None) -> dict:
    git_sha = "a" * 40
    source_sha = "b" * 64
    manifest_sha = "c" * 64
    binding = {
        "git_sha": git_sha,
        "product_version": "0.9.0",
        "architecture": "arm64",
        "runtime_wave": 76,
        "candidate_guard_wave": 84,
        "certification_guard_wave": 84,
        "source_contract_wave": 95,
        "source_release_state": "PREPARED_RELEASE",
        "source_release_tag": "v0.9.0",
        "candidate_source_sha256": source_sha,
        "candidate_manifest_sha256": manifest_sha,
        "build_origin": {"event": "push", "ref": "refs/heads/main", "trusted_for_physical_uat": True},
        "provenance_schema": "binario.marketing.full-mac-build.v4",
    }
    core = {
        "schema": module.SCHEMA,
        "binding": binding,
        "phase_a": {
            "session_id": "session-1",
            "evidence_sha256": "d" * 64,
            "required_scenarios": 5,
            "passed_scenarios": 5,
            "finished_at": "2026-08-24T03:00:00+00:00",
            "report_sha256": "e" * 64,
        },
        "phase_b": {
            "required_gates": 12,
            "passed_gates": 12,
            "overall": "UAT_PASS",
            "updated_at": "2026-08-24T03:05:00+00:00",
            "report_sha256": "f" * 64,
        },
        "both_phases_passed": True,
        "release_authority": False,
        "publication_authority": False,
        "production_ready": False,
    }
    if include_w97:
        handoff = {
            "schema": module.W97_HANDOFF_SCHEMA,
            "git_sha": git_sha,
            "role": "PHYSICAL_UAT_CANDIDATE_ONLY",
            "physical_uat_eligible": True,
            "architecture": "arm64",
            "runtime_wave": 76,
            "certification_guard_wave": 84,
            "operator_handoff_wave": 84,
            "combined_attestation_wave": 85,
            "source_contract_wave": 95,
            "source_release_state": "PREPARED_RELEASE",
            "source_release_tag": "v0.9.0",
            "candidate_source_sha256": source_sha,
            "actual_candidate_source_sha256": extracted_source_sha or source_sha,
            "candidate_manifest_sha256": manifest_sha,
            "host": {"system": "Darwin", "machine": "arm64", "is_ci": False, "physical_gate_eligible": True},
        }
        core["w97_integrity"] = {
            "schema": module.W97_INTEGRITY_SCHEMA,
            "handoff_verification_sha256": "9" * 64,
            "handoff_verification": handoff,
            "bundle_signature_verified": True,
            "codesign_requirement": ["--deep", "--strict"],
            "source_digest_reverified": True,
            "physical_host_reverified": True,
        }
    return {**core, "generated_at": "2026-08-24T03:06:00+00:00", "attestation_sha256": module._digest(core)}


class Wave97FinalIntegrityTransportTests(unittest.TestCase):
    def test_prepared_attestation_requires_and_verifies_w97_final_integrity(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "combined.json"
            row = _prepared_attestation(module)
            path.write_text(json.dumps(row), encoding="utf-8")
            report = module.verify(
                path,
                expected_git_sha="a" * 40,
                expected_source_release_state="PREPARED_RELEASE",
                expected_release_tag="v0.9.0",
            )
            self.assertTrue(report["w97_integrity_required"])
            self.assertTrue(report["w97_integrity_verified"])
            self.assertEqual(report["w97_handoff_verification_sha256"], "9" * 64)

    def test_prepared_attestation_without_w97_seal_is_rejected_even_with_valid_digest(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "combined.json"
            row = _prepared_attestation(module, include_w97=False)
            path.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "requires W97 final integrity"):
                module.verify(path, expected_source_release_state="PREPARED_RELEASE", expected_release_tag="v0.9.0")

    def test_w97_embedded_handoff_must_prove_extracted_source_digest(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "combined.json"
            row = _prepared_attestation(module, extracted_source_sha="0" * 64)
            path.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "extracted source digest mismatch"):
                module.verify(path, expected_source_release_state="PREPARED_RELEASE", expected_release_tag="v0.9.0")

    def test_finalize_command_rechecks_codesign_after_legacy_finalizer_before_w97_seal(self):
        source = FINALIZE_COMMAND.read_text(encoding="utf-8")
        self.assertGreaterEqual(source.count('codesign --verify --deep --strict "$APP"'), 2)
        finalizer = source.index('"$PY" -I -B "$FINALIZER"')
        second_codesign = source.index('codesign --verify --deep --strict "$APP"', finalizer)
        seal = source.index('core["w97_integrity"]', second_codesign)
        self.assertLess(finalizer, second_codesign)
        self.assertLess(second_codesign, seal)
        self.assertIn("handoff_verification_sha256", source)
        self.assertIn("actual_candidate_source_sha256", source)
        self.assertIn("bundle_signature_verified", source)
        self.assertIn("release_authority\": False", source)


if __name__ == "__main__":
    unittest.main()
