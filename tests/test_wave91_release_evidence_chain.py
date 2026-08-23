from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_evidence_chain.py"
AUDIT_SCRIPT = ROOT / "scripts" / "release_enablement_audit.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"


def _module(path: Path = SCRIPT):
    spec = importlib.util.spec_from_file_location(f"wave91_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Wave91ReleaseEvidenceChainTests(unittest.TestCase):
    def _asset_fixture(
        self,
        module,
        root: Path,
        architecture: str,
        *,
        git_sha: str = "a" * 40,
        source_sha: str = "b" * 64,
        attestation_sha: str = "c" * 64,
        attestation_file_sha: str = "d" * 64,
        candidate_manifest_sha: str = "e" * 64,
    ):
        asset = root / f"Binario-Marketing-IA-v1.0.0-{architecture}.zip"
        asset.write_bytes(f"asset:{architecture}".encode("utf-8"))
        evidence_path = root / f"RELEASE-EVIDENCE-{architecture}.json"
        rebuild_sha = "f" * 64
        trust_digest = "1" * 64
        trust_file_sha = "2" * 64
        payload = {
            "schema": module.ASSET_SCHEMA,
            "tag": "v1.0.0",
            "git_sha": git_sha,
            "architecture": architecture,
            "product_version": "1.0.0",
            "runtime_wave": module.RUNTIME_WAVE,
            "certification_guard_wave": module.CERTIFICATION_GUARD_WAVE,
            "source_sha256": source_sha,
            "evidence_file_name": evidence_path.name,
            "asset": {"name": asset.name, "sha256": _sha256(asset), "size_bytes": asset.stat().st_size},
            "physical_uat": {"schema": module.COMBINED_UAT_SCHEMA, "attestation_sha256": attestation_sha, "evidence_file_sha256": attestation_file_sha, "candidate_source_sha256": source_sha, "candidate_manifest_sha256": candidate_manifest_sha, "physical_architecture": "arm64"},
            "distribution_rebuild": {"schema": module.DISTRIBUTION_REBUILD_SCHEMA, "purpose": module.DISTRIBUTION_REBUILD_PURPOSE, "manifest_sha256": rebuild_sha, "source_sha256": source_sha, "build_origin": {"event": "push", "ref": "refs/tags/v1.0.0", "eligible_distribution_origin": True}},
            "distribution_trust": {"schema": "binario.marketing.distribution-trust.v1", "evidence_sha256": trust_digest, "evidence_file_sha256": trust_file_sha, "notary_submission_id": f"notary-{architecture}"},
            "production_gate": {"schema": module.PRODUCTION_GATE_SCHEMA, "evidence_file_sha256": "3" * 64, "stage": "PRODUCTION_READY", "uat_binding_mode": "source_equivalent_arm64_rebuild" if architecture == "arm64" else "source_equivalent_cross_arch_distribution", "uat_evidence_file_sha256": attestation_file_sha, "uat_attestation_sha256": attestation_sha, "distribution_evidence_file_sha256": trust_file_sha, "distribution_trust_evidence_sha256": trust_digest, "distribution_rebuild_manifest_sha256": rebuild_sha},
            "build_inputs": {"build_provenance_sha256": "4" * 64, "embedded_readiness_sha256": "5" * 64},
            "authorization_gates": {"canonical_release_contract": True, "exact_git_sha_binding": True, "tag_version_binding": True, "physical_uat_attestation_verified": True, "source_equivalence_verified": True, "distribution_rebuild_verified": True, "developer_id_signature_verified": True, "apple_notarization_verified": True, "gatekeeper_verified": True, "production_gate_passed": True, "exact_evidence_digest_binding_verified": True, "immutable_asset_hashed": True},
            "asset_authorized": True,
            "operational_authorization": False,
            "release_authority": False,
            "publication_authority": False,
            "production_ready": False,
            "mutations_performed": False,
        }
        evidence = module._seal(payload, "evidence_sha256")
        evidence_path.write_text(json.dumps(evidence, sort_keys=True), encoding="utf-8")
        manifest_path = root / f"RELEASE-{architecture}.json"
        manifest_path.write_text(json.dumps(module.build_release_manifest(evidence), sort_keys=True), encoding="utf-8")
        return evidence_path, manifest_path, asset

    def test_valid_cross_arch_chain_is_the_only_place_release_authority_appears(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            arm_evidence, arm_manifest, _ = self._asset_fixture(module, root, "arm64")
            x86_evidence, x86_manifest, _ = self._asset_fixture(module, root, "x86_64")
            arm = module.verify_asset_evidence(arm_evidence, asset_dir=root, release_manifest=arm_manifest)
            x86 = module.verify_asset_evidence(x86_evidence, asset_dir=root, release_manifest=x86_manifest)
            self.assertFalse(arm["release_authority"])
            self.assertFalse(x86["release_authority"])
            authorization = module.build_release_authorization(arm, x86)
            self.assertTrue(authorization["operational_authorization"])
            self.assertTrue(authorization["release_authority"])
            self.assertTrue(authorization["publication_authority"])
            self.assertTrue(authorization["production_ready"])
            self.assertTrue(authorization["cross_architecture_gates"]["each_native_chain_has_exact_evidence_binding"])
            self.assertFalse(authorization["publication_performed"])
            self.assertFalse(authorization["mutations_performed"])

    def test_asset_tampering_invalidates_evidence(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            evidence, manifest, asset = self._asset_fixture(module, root, "arm64")
            asset.write_bytes(asset.read_bytes() + b"tampered")
            with self.assertRaisesRegex(ValueError, "asset digest mismatch"):
                module.verify_asset_evidence(evidence, asset_dir=root, release_manifest=manifest)

    def test_cross_arch_source_mismatch_blocks_authorization(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            arm_evidence, arm_manifest, _ = self._asset_fixture(module, root, "arm64", source_sha="b" * 64)
            x86_evidence, x86_manifest, _ = self._asset_fixture(module, root, "x86_64", source_sha="9" * 64)
            arm = module.verify_asset_evidence(arm_evidence, asset_dir=root, release_manifest=arm_manifest)
            x86 = module.verify_asset_evidence(x86_evidence, asset_dir=root, release_manifest=x86_manifest)
            with self.assertRaisesRegex(ValueError, "source_sha256 mismatch"):
                module.build_release_authorization(arm, x86)

    def test_cross_arch_uat_mismatch_blocks_authorization(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            arm_evidence, arm_manifest, _ = self._asset_fixture(module, root, "arm64", attestation_sha="c" * 64)
            x86_evidence, x86_manifest, _ = self._asset_fixture(module, root, "x86_64", attestation_sha="8" * 64)
            arm = module.verify_asset_evidence(arm_evidence, asset_dir=root, release_manifest=arm_manifest)
            x86 = module.verify_asset_evidence(x86_evidence, asset_dir=root, release_manifest=x86_manifest)
            with self.assertRaisesRegex(ValueError, "UAT attestation_sha256 mismatch"):
                module.build_release_authorization(arm, x86)

    def test_production_gate_digest_mismatch_blocks_native_chain(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            evidence_path, manifest_path, _ = self._asset_fixture(module, root, "arm64")
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["production_gate"]["uat_evidence_file_sha256"] = "9" * 64
            evidence = module._seal(evidence, "evidence_sha256")
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            manifest_path.write_text(json.dumps(module.build_release_manifest(evidence)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "production gate/UAT file digest mismatch"):
                module.verify_asset_evidence(evidence_path, asset_dir=root, release_manifest=manifest_path)

    def test_per_arch_evidence_cannot_self_grant_release_authority(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            evidence_path, manifest_path, _ = self._asset_fixture(module, root, "arm64")
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            evidence["release_authority"] = True
            evidence = module._seal(evidence, "evidence_sha256")
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            manifest_path.write_text(json.dumps(module.build_release_manifest(evidence)), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "must not carry release authority"):
                module.verify_asset_evidence(evidence_path, asset_dir=root, release_manifest=manifest_path)

    def test_authorization_tamper_is_detected(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            arm_evidence, arm_manifest, _ = self._asset_fixture(module, root, "arm64")
            x86_evidence, x86_manifest, _ = self._asset_fixture(module, root, "x86_64")
            arm = module.verify_asset_evidence(arm_evidence, asset_dir=root, release_manifest=arm_manifest)
            x86 = module.verify_asset_evidence(x86_evidence, asset_dir=root, release_manifest=x86_manifest)
            authorization = module.build_release_authorization(arm, x86)
            authorization_path = root / "RELEASE-AUTHORIZATION.json"
            authorization["publication_authority"] = False
            authorization_path.write_text(json.dumps(authorization), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "authorization manifest drift"):
                module.verify_release_authorization(authorization_path, arm64_evidence=arm_evidence, x86_evidence=x86_evidence, asset_dir=root, arm64_release_manifest=arm_manifest, x86_release_manifest=x86_manifest, expected_tag="v1.0.0", expected_git_sha="a" * 40)

    def test_production_gate_must_be_actual_pass_not_merely_present(self):
        module = _module()
        gate = {"schema": module.PRODUCTION_GATE_SCHEMA, "git_sha": "a" * 40, "architecture": "arm64", "version": "1.0.0", "stage": "RELEASE_CANDIDATE_BLOCKED", "production_ready": False, "blocker_codes": ["physical_uat_missing"], "distribution_trust_verified": True, "distribution_rebuild_consistent": True, "uat_binding_mode": "source_equivalent_arm64_rebuild", "source_equivalent_authorization": True}
        with self.assertRaises(ValueError):
            module._validate_production_gate(gate, git_sha="a" * 40, architecture="arm64", product_version="1.0.0")

    def test_production_gate_exact_evidence_inputs_are_fail_closed(self):
        module = _module()
        gate = {"schema": module.PRODUCTION_GATE_SCHEMA, "git_sha": "a" * 40, "architecture": "arm64", "version": "1.0.0", "stage": "PRODUCTION_READY", "production_ready": True, "blocker_codes": [], "distribution_trust_verified": True, "distribution_rebuild_consistent": True, "uat_binding_mode": "source_equivalent_arm64_rebuild", "source_equivalent_authorization": True, "uat_evidence_file_sha256": "1" * 64, "uat_attestation_sha256": "2" * 64, "distribution_evidence_file_sha256": "3" * 64, "distribution_trust_evidence_sha256": "4" * 64, "distribution_rebuild_manifest_sha256": "5" * 64}
        with self.assertRaisesRegex(ValueError, "uat_evidence_file_sha256"):
            module._validate_production_gate(gate, git_sha="a" * 40, architecture="arm64", product_version="1.0.0", uat_evidence_file_sha256="9" * 64, uat_attestation_sha256="2" * 64, distribution_evidence_file_sha256="3" * 64, distribution_trust_evidence_sha256="4" * 64, distribution_rebuild_manifest_sha256="5" * 64)

    def test_release_manifest_is_v2_and_guarded_by_w91(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            evidence_path, _, _ = self._asset_fixture(module, root, "arm64")
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            manifest = module.build_release_manifest(evidence)
            self.assertEqual(manifest["schema"], "binario.marketing.release.v2")
            self.assertEqual(manifest["certification_guard_wave"], 91)
            self.assertEqual(manifest["release_evidence_sha256"], evidence["evidence_sha256"])
            self.assertFalse(manifest["release_authority"])

    def test_workflow_persists_gate_builds_chain_and_authorizes_before_publication(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        gate = workflow.find("production-gate-${{ matrix.arch }}.json")
        asset_chain = workflow.find("release_evidence_chain.py write-asset")
        cross_arch = workflow.find("release_evidence_chain.py authorize")
        verify_auth = workflow.find("release_evidence_chain.py verify-authorization")
        publish = workflow.find("publish_release_transaction.sh")
        self.assertTrue(0 <= gate < asset_chain < cross_arch < verify_auth < publish, (gate, asset_chain, cross_arch, verify_auth, publish))
        self.assertIn("RELEASE-AUTHORIZATION.json", workflow)

    def test_source_audit_remains_fail_closed_and_knows_w91_runtime_gate(self):
        audit = _module(AUDIT_SCRIPT).audit(ROOT)
        self.assertEqual(audit["status"], "BLOCKED")
        self.assertEqual(audit["runtime_wave"], 76)
        self.assertGreaterEqual(audit["certification_guard_wave"], 91)
        self.assertFalse(audit["operational_authorization"])
        self.assertFalse(audit["release_authority"])
        self.assertFalse(audit["production_ready"])
        self.assertIn("cross_arch_release_authorization_verified_at_tag_runtime", audit["external_runtime_requirements"])
        self.assertTrue(audit["structural_gates"]["release_evidence_chain"])
        self.assertTrue(audit["structural_gates"]["cross_arch_release_authorization_before_publish"])
        self.assertTrue(audit["structural_gates"]["final_authorization_verification_before_publish"])


if __name__ == "__main__":
    unittest.main()
