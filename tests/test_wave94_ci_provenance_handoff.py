from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_ci_provenance_authorization.py"
TRANSACTION = ROOT / "scripts" / "publish_release_transaction.sh"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"


def _module():
    spec = importlib.util.spec_from_file_location("wave94_ci_provenance", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _provenance(module, *, arch: str, asset: str, sha: str) -> dict:
    repository = "arendon7/MKTGAPP"
    return {
        "asset": asset,
        "asset_sha256": sha,
        "bundle_sha256": "9" * 64,
        "repository": repository,
        "signer_workflow": f"{repository}/.github/workflows/persistent-release.yml",
        "source_ref": "refs/tags/v1.0.0",
        "source_digest": "a" * 40,
        "predicate_type": module.PREDICATE_TYPE,
        "oidc_issuer": module.GITHUB_OIDC_ISSUER,
        "deny_self_hosted_runners": True,
        "verified_attestation_count": 1,
        "matching_subject_count": 1,
        "verified_timestamp_count": 1,
        "cryptographic_attestation_verified": True,
    }


class Wave94CiProvenanceHandoffTests(unittest.TestCase):
    def test_schema_guard_and_transaction_handoff_are_w94(self):
        module = _module()
        self.assertEqual(module.SCHEMA, "binario.marketing.release-ci-provenance-authorization.v2")
        self.assertEqual(module.CERTIFICATION_GUARD_WAVE, 94)
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("transaction_handoff_authority", source)
        self.assertIn("publication_authority\": False", source)
        self.assertIn("verify-transaction-handoff", source)

    def test_authorization_binds_both_exact_assets_and_transaction_script(self):
        module = _module()
        repository = "arendon7/MKTGAPP"
        arm_name = "Binario-Marketing-IA-v1.0.0-arm64.zip"
        x86_name = "Binario-Marketing-IA-v1.0.0-x86_64.zip"
        arm_sha = "1" * 64
        x86_sha = "2" * 64
        w92 = {
            "schema": "binario.marketing.release-artifact-authorization.v1",
            "tag": "v1.0.0",
            "git_sha": "a" * 40,
            "product_version": "1.0.0",
            "source_sha256": "b" * 64,
            "authorization_sha256": "c" * 64,
            "publication_authority": True,
            "production_ready": True,
            "publication_performed": False,
            "mutations_performed": False,
            "native_assets": {
                "arm64": {"asset": arm_name, "asset_sha256": arm_sha},
                "x86_64": {"asset": x86_name, "asset_sha256": x86_sha},
            },
        }
        authorization = module.build_authorization(
            w92=w92,
            arm64_provenance=_provenance(module, arch="arm64", asset=arm_name, sha=arm_sha),
            x86_provenance=_provenance(module, arch="x86_64", asset=x86_name, sha=x86_sha),
            repository=repository,
            signer_workflow=f"{repository}/.github/workflows/persistent-release.yml",
            source_ref="refs/tags/v1.0.0",
            source_digest="a" * 40,
            transaction_script_sha256="d" * 64,
        )
        self.assertEqual(authorization["certification_guard_wave"], 94)
        self.assertTrue(authorization["transaction_handoff_authority"])
        self.assertFalse(authorization["publication_authority"])
        self.assertTrue(authorization["production_ready"])
        self.assertEqual(authorization["transaction"]["script_sha256"], "d" * 64)
        self.assertTrue(authorization["provenance_handoff_gates"]["exact_native_asset_digests_attested"])

    def test_transaction_rejects_authorization_if_its_own_bytes_change(self):
        module = _module()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            transaction = root / "publish_release_transaction.sh"
            transaction.write_text("echo original\n", encoding="utf-8")
            auth = {
                "schema": module.SCHEMA,
                "tag": "v1.0.0",
                "git_sha": "a" * 40,
                "transaction": {
                    "script": "scripts/publish_release_transaction.sh",
                    "script_sha256": module._sha256_file(transaction),
                },
                "transaction_handoff_authority": True,
                "publication_authority": False,
                "production_ready": True,
                "publication_performed": False,
                "mutations_performed": False,
            }
            auth = module._seal(auth)
            evidence = root / "authorization.json"
            evidence.write_text(json.dumps(auth), encoding="utf-8")
            transaction.write_text("echo changed\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "transaction script digest mismatch"):
                module.verify_transaction_handoff(
                    evidence,
                    transaction_script=transaction,
                    expected_tag="v1.0.0",
                    expected_git_sha="a" * 40,
                )

    def test_w93_transaction_requires_w94_before_any_github_mutation(self):
        transaction = TRANSACTION.read_text(encoding="utf-8")
        handoff = transaction.index("W94_STAGE_PROVENANCE_HANDOFF")
        preexisting = transaction.index("W93_STAGE_PREEXISTING_RELEASE_CHECK")
        create = transaction.index("W93_STAGE_DRAFT_CREATE")
        self.assertLess(handoff, preexisting)
        self.assertLess(preexisting, create)
        self.assertIn("RELEASE-CI-PROVENANCE-AUTHORIZATION.json", transaction)
        self.assertIn("verify-transaction-handoff", transaction)

    def test_workflow_will_keep_w93_transaction_as_final_mutation_boundary(self):
        source = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("bash scripts/publish_release_transaction.sh", source)
        # W94 provenance authorization must be inserted before this call; the
        # transaction itself remains the only GitHub Release mutation surface.
        self.assertNotIn("gh release create", source)


if __name__ == "__main__":
    unittest.main()
