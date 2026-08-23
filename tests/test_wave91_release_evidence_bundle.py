from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_evidence_bundle.py"
WORKFLOW = ROOT / ".github/workflows/persistent-release.yml"


def _load_module():
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        spec = importlib.util.spec_from_file_location("wave91_release_evidence_bundle", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module
    finally:
        try:
            sys.path.remove(str(ROOT / "scripts"))
        except ValueError:
            pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Wave91ReleaseEvidenceBundleTests(unittest.TestCase):
    def _fixture(self, root: Path):
        uat = root / "PHYSICAL-UAT-ATTESTATION.json"
        trust = root / "DISTRIBUTION-TRUST-arm64.json"
        gate = root / "PRODUCTION-GATE-arm64.json"
        uat.write_text('{"uat":"exact"}\n', encoding="utf-8")
        trust.write_text('{"trust":"exact"}\n', encoding="utf-8")
        uat_sha = _sha(uat)
        trust_sha = _sha(trust)
        trust_digest = "1" * 64
        rebuild_sha = "2" * 64
        gate_payload = {
            "uat_evidence_file_sha256": uat_sha,
            "uat_attestation_sha256": "3" * 64,
            "distribution_evidence_file_sha256": trust_sha,
            "distribution_trust_evidence_sha256": trust_digest,
            "distribution_rebuild_manifest_sha256": rebuild_sha,
        }
        gate.write_text(json.dumps(gate_payload, sort_keys=True) + "\n", encoding="utf-8")
        evidence = {
            "architecture": "arm64",
            "git_sha": "a" * 40,
            "tag": "v1.0.0",
            "evidence_sha256": "4" * 64,
            "asset": {"sha256": "5" * 64},
            "physical_uat": {
                "evidence_file_sha256": uat_sha,
                "attestation_sha256": "3" * 64,
            },
            "distribution_trust": {
                "evidence_file_sha256": trust_sha,
                "evidence_sha256": trust_digest,
            },
            "distribution_rebuild": {"manifest_sha256": rebuild_sha},
            "production_gate": {"evidence_file_sha256": _sha(gate)},
        }
        return uat, trust, gate, evidence

    def test_exact_published_evidence_bytes_are_verified(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uat, trust, gate, evidence = self._fixture(root)
            with mock.patch.object(module, "verify_asset_evidence", return_value=evidence):
                report = module.verify_bundle(
                    evidence_path=root / "RELEASE-EVIDENCE-arm64.json",
                    asset_dir=root,
                    release_manifest=root / "RELEASE-arm64.json",
                    uat_evidence=uat,
                    distribution_evidence=trust,
                    production_gate_evidence=gate,
                    expected_tag="v1.0.0",
                    expected_git_sha="a" * 40,
                )
            self.assertTrue(report["exact_published_evidence_verified"])
            self.assertFalse(report["release_authority"])
            self.assertFalse(report["publication_authority"])

    def test_substituted_distribution_evidence_is_blocked(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uat, trust, gate, evidence = self._fixture(root)
            trust.write_text('{"trust":"substituted"}\n', encoding="utf-8")
            with mock.patch.object(module, "verify_asset_evidence", return_value=evidence):
                with self.assertRaisesRegex(ValueError, "distribution trust bytes"):
                    module.verify_bundle(
                        evidence_path=root / "RELEASE-EVIDENCE-arm64.json",
                        asset_dir=root,
                        release_manifest=root / "RELEASE-arm64.json",
                        uat_evidence=uat,
                        distribution_evidence=trust,
                        production_gate_evidence=gate,
                    )

    def test_production_gate_must_bind_the_same_exact_inputs(self):
        module = _load_module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            uat, trust, gate, evidence = self._fixture(root)
            gate_payload = json.loads(gate.read_text(encoding="utf-8"))
            gate_payload["uat_attestation_sha256"] = "9" * 64
            gate.write_text(json.dumps(gate_payload, sort_keys=True) + "\n", encoding="utf-8")
            evidence["production_gate"]["evidence_file_sha256"] = _sha(gate)
            with mock.patch.object(module, "verify_asset_evidence", return_value=evidence):
                with self.assertRaisesRegex(ValueError, "uat_attestation_sha256"):
                    module.verify_bundle(
                        evidence_path=root / "RELEASE-EVIDENCE-arm64.json",
                        asset_dir=root,
                        release_manifest=root / "RELEASE-arm64.json",
                        uat_evidence=uat,
                        distribution_evidence=trust,
                        production_gate_evidence=gate,
                    )

    def test_publish_job_invokes_exact_bundle_verifier_before_authorization(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        bundle = workflow.find("verify_release_evidence_bundle.py")
        authorize = workflow.find("release_evidence_chain.py authorize")
        publish = workflow.find("publish_release_transaction.sh")
        self.assertTrue(0 <= bundle < authorize < publish, (bundle, authorize, publish))
        self.assertIn("--uat-evidence release/PHYSICAL-UAT-ATTESTATION.json", workflow)
        self.assertIn('--production-gate-evidence "release/PRODUCTION-GATE-${arch}.json"', workflow)


if __name__ == "__main__":
    unittest.main()
