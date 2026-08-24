from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_ci_provenance_authorization.py"


def _module():
    spec = importlib.util.spec_from_file_location("wave94_ci_provenance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _provenance(*, arch: str, digest: str) -> dict:
    return {
        "asset": f"Binario-Marketing-IA-v1.0.0-{arch}.zip",
        "asset_sha256": digest,
        "bundle_sha256": "d" * 64,
        "repository": "arendon7/MKTGAPP",
        "signer_workflow": "arendon7/MKTGAPP/.github/workflows/persistent-release.yml",
        "source_ref": "refs/tags/v1.0.0",
        "source_digest": "a" * 40,
        "predicate_type": "https://slsa.dev/provenance/v1",
        "oidc_issuer": "https://token.actions.githubusercontent.com",
        "deny_self_hosted_runners": True,
        "verified_attestation_count": 1,
        "matching_subject_count": 1,
        "verified_timestamp_count": 1,
        "cryptographic_attestation_verified": True,
    }


def _w92() -> dict:
    return {
        "schema": "binario.marketing.release-artifact-authorization.v1",
        "tag": "v1.0.0",
        "git_sha": "a" * 40,
        "product_version": "1.0.0",
        "runtime_wave": 76,
        "source_sha256": "b" * 64,
        "authorization_sha256": "c" * 64,
        "native_assets": {
            "arm64": {"asset": "Binario-Marketing-IA-v1.0.0-arm64.zip", "asset_sha256": "1" * 64},
            "x86_64": {"asset": "Binario-Marketing-IA-v1.0.0-x86_64.zip", "asset_sha256": "2" * 64},
        },
        "publication_authority": True,
        "production_ready": True,
        "publication_performed": False,
        "mutations_performed": False,
    }


def _build(module, transaction_sha: str) -> dict:
    return module.build_authorization(
        w92=_w92(),
        arm64_provenance=_provenance(arch="arm64", digest="1" * 64),
        x86_provenance=_provenance(arch="x86_64", digest="2" * 64),
        repository="arendon7/MKTGAPP",
        signer_workflow="arendon7/MKTGAPP/.github/workflows/persistent-release.yml",
        source_ref="refs/tags/v1.0.0",
        source_digest="a" * 40,
        transaction_script_sha256=transaction_sha,
    )


class Wave94CIProvenanceAuthorizationTests(unittest.TestCase):
    def test_verification_command_is_exact_identity_bound_and_bundle_based(self):
        module = _module()
        command = module._verification_command(
            asset=Path("release/app.zip"),
            bundle=Path("release/provenance.json"),
            repository="arendon7/MKTGAPP",
            signer_workflow="arendon7/MKTGAPP/.github/workflows/persistent-release.yml",
            source_ref="refs/tags/v1.0.0",
            source_digest="a" * 40,
        )
        joined = " ".join(command)
        for marker in (
            "gh attestation verify",
            "--bundle release/provenance.json",
            "--repo arendon7/MKTGAPP",
            "--signer-workflow arendon7/MKTGAPP/.github/workflows/persistent-release.yml",
            "--source-ref refs/tags/v1.0.0",
            f"--source-digest {'a' * 40}",
            "--cert-oidc-issuer https://token.actions.githubusercontent.com",
            "--deny-self-hosted-runners",
            "--predicate-type https://slsa.dev/provenance/v1",
            "--format json",
        ):
            self.assertIn(marker, joined)

    def test_verified_output_requires_exact_subject_digest_name_and_timestamp(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "artifact.zip"
            asset.write_bytes(b"exact-release-bytes")
            digest = module._sha256_file(asset)
            output = [{
                "verificationResult": {
                    "statement": {
                        "predicateType": module.PREDICATE_TYPE,
                        "subject": [{"name": "release/artifact.zip", "digest": {"sha256": digest}}],
                    },
                    "verifiedTimestamps": [{"type": "rekor"}],
                }
            }]
            report = module._validate_verification_output(output, asset=asset)
            self.assertEqual(report["subject_sha256"], digest)
            self.assertEqual(report["matching_subject_count"], 1)
            self.assertEqual(report["verified_timestamp_count"], 1)

            output[0]["verificationResult"]["statement"]["subject"][0]["digest"]["sha256"] = "0" * 64
            with self.assertRaisesRegex(ValueError, "exact asset"):
                module._validate_verification_output(output, asset=asset)

    def test_verified_output_rejects_missing_transparency_witness(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmp:
            asset = Path(tmp) / "artifact.zip"
            asset.write_bytes(b"bytes")
            digest = module._sha256_file(asset)
            output = [{
                "verificationResult": {
                    "statement": {
                        "predicateType": module.PREDICATE_TYPE,
                        "subject": [{"name": "artifact.zip", "digest": {"sha256": digest}}],
                    },
                    "verifiedTimestamps": [],
                }
            }]
            with self.assertRaisesRegex(ValueError, "timestamp"):
                module._validate_verification_output(output, asset=asset)

    def test_valid_w94_is_transaction_handoff_not_publication_authority(self):
        module = _module()
        report = _build(module, "e" * 64)
        self.assertEqual(report["schema"], "binario.marketing.release-ci-provenance-authorization.v2")
        self.assertEqual(report["runtime_wave"], 76)
        self.assertEqual(report["certification_guard_wave"], 94)
        self.assertTrue(report["transaction_handoff_authority"])
        self.assertTrue(report["release_authority"])
        self.assertFalse(report["publication_authority"])
        self.assertTrue(report["production_ready"])
        self.assertFalse(report["publication_performed"])
        self.assertFalse(report["mutations_performed"])
        self.assertEqual(report["transaction"]["script_sha256"], "e" * 64)
        self.assertEqual(len(report["authorization_sha256"]), 64)

    def test_cross_arch_asset_and_identity_drift_are_fail_closed(self):
        module = _module()
        x86 = _provenance(arch="x86_64", digest="9" * 64)
        with self.assertRaisesRegex(ValueError, "W92/provenance asset digest mismatch"):
            module.build_authorization(
                w92=_w92(), arm64_provenance=_provenance(arch="arm64", digest="1" * 64), x86_provenance=x86,
                repository="arendon7/MKTGAPP",
                signer_workflow="arendon7/MKTGAPP/.github/workflows/persistent-release.yml",
                source_ref="refs/tags/v1.0.0", source_digest="a" * 40,
                transaction_script_sha256="e" * 64,
            )

        x86 = _provenance(arch="x86_64", digest="2" * 64)
        x86["signer_workflow"] = "arendon7/MKTGAPP/.github/workflows/other.yml"
        with self.assertRaisesRegex(ValueError, "signer workflow mismatch"):
            module.build_authorization(
                w92=_w92(), arm64_provenance=_provenance(arch="arm64", digest="1" * 64), x86_provenance=x86,
                repository="arendon7/MKTGAPP",
                signer_workflow="arendon7/MKTGAPP/.github/workflows/persistent-release.yml",
                source_ref="refs/tags/v1.0.0", source_digest="a" * 40,
                transaction_script_sha256="e" * 64,
            )

    def test_w92_cannot_be_reused_for_different_tag_or_commit(self):
        module = _module()
        with self.assertRaisesRegex(ValueError, "W92/source digest mismatch"):
            module.build_authorization(
                w92=_w92(),
                arm64_provenance=_provenance(arch="arm64", digest="1" * 64),
                x86_provenance=_provenance(arch="x86_64", digest="2" * 64),
                repository="arendon7/MKTGAPP",
                signer_workflow="arendon7/MKTGAPP/.github/workflows/persistent-release.yml",
                source_ref="refs/tags/v1.0.0", source_digest="f" * 40,
                transaction_script_sha256="e" * 64,
            )

    def test_transaction_handoff_binds_seal_tag_commit_and_exact_publisher_bytes(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transaction = root / "publish_release_transaction.sh"
            transaction.write_text("#!/bin/bash\necho publish\n", encoding="utf-8")
            report = _build(module, module._sha256_file(transaction))
            authorization = root / "authorization.json"
            authorization.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            verified = module.verify_transaction_handoff(
                authorization,
                transaction_script=transaction,
                expected_tag="v1.0.0",
                expected_git_sha="a" * 40,
            )
            self.assertTrue(verified["transaction_handoff_authority"])
            self.assertFalse(verified["publication_authority"])

            transaction.write_text("#!/bin/bash\necho tampered\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "transaction script digest mismatch"):
                module.verify_transaction_handoff(
                    authorization,
                    transaction_script=transaction,
                    expected_tag="v1.0.0",
                    expected_git_sha="a" * 40,
                )

    def test_tampered_authorization_seal_is_blocked(self):
        module = _module()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transaction = root / "publish_release_transaction.sh"
            transaction.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            report = _build(module, module._sha256_file(transaction))
            report["transaction_handoff_authority"] = False
            authorization = root / "authorization.json"
            authorization.write_text(json.dumps(report), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                module.verify_transaction_handoff(
                    authorization,
                    transaction_script=transaction,
                    expected_tag="v1.0.0",
                    expected_git_sha="a" * 40,
                )


if __name__ == "__main__":
    unittest.main()
