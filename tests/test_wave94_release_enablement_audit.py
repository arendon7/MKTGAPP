from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "release_enablement_audit.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"
PUBLISHER = ROOT / "scripts" / "publish_release_transaction.sh"
AUTH = ROOT / "scripts" / "release_ci_provenance_authorization.py"
VERSION = ROOT / "src" / "binario_marketing" / "version.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave94ReleaseEnablementAuditTests(unittest.TestCase):
    def test_source_preserves_guard_94_under_later_guards_and_is_prepared(self):
        report = _module(AUDIT, "w94_audit").audit(ROOT)
        self.assertTrue(report["schema"].startswith("binario.marketing.release-enablement-audit.v"))
        self.assertEqual(report["runtime_wave"], 76)
        self.assertGreaterEqual(report["certification_guard_wave"], 94)
        self.assertEqual(report["status"], "AWAITING_OPERATIONAL_AUTHORIZATION")
        self.assertEqual(report["source_status"], "SOURCE_CONTRACT_READY")
        self.assertEqual(report["source_release_state"], "PREPARED_RELEASE")
        self.assertEqual(report["blocker_codes"], [])
        self.assertFalse(report["operational_authorization"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["publication_authority"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["mutations_performed"])

    def test_all_historical_and_w94_structural_gates_are_present(self):
        report = _module(AUDIT, "w94_structure").audit(ROOT)
        missing = [name for name, ok in report["structural_gates"].items() if ok is not True]
        self.assertEqual(missing, [], report)
        for name in (
            "w93_publication_is_transactional",
            "w94_provenance_action_pinned",
            "w94_provenance_uses_exact_packaged_path",
            "w94_sigstore_bundle_persisted",
            "w94_attestation_after_roundtrip_before_native_upload",
            "w94_build_job_has_oidc_attestation_permissions",
            "w94_global_permissions_are_read_only",
            "w94_publish_job_contents_write_is_scoped",
            "w94_ci_provenance_authorization_schema",
            "w94_uses_github_oidc_and_slsa",
            "w94_denies_self_hosted_attestations",
            "w94_binds_repo_workflow_ref_and_digest",
            "w94_transaction_script_hash_bound",
            "w94_handoff_is_non_publication_authority",
            "w94_authorization_after_w92_before_w93",
            "w94_authorization_manifest_required",
            "w94_transaction_handoff_precedes_any_w93_mutation",
            "w94_transaction_handoff_verifies_exact_publisher",
        ):
            self.assertTrue(report["structural_gates"][name], name)

    def test_w94_attests_after_w92_roundtrip_and_before_artifact_transport(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        package = workflow.index("Package immutable release asset")
        roundtrip = workflow.index("Verify W92 packaged artifact round-trip trust")
        attest = workflow.index("Attest exact release ZIP with GitHub OIDC provenance")
        upload = workflow.index("uses: actions/upload-artifact@v4", attest)
        self.assertTrue(package < roundtrip < attest < upload)
        self.assertIn("subject-path: ${{ steps.package.outputs.zip_path }}", workflow)
        self.assertIn("steps.attest.outputs.bundle-path", workflow)

    def test_w94_full_authorization_is_after_w92_and_before_w93_transaction(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        w92 = workflow.index("Verify W92 final publication authorization")
        w94_build = workflow.index("Build W94 CI provenance transaction handoff")
        w94_verify = workflow.index("Verify W94 CI provenance transaction handoff")
        w93 = workflow.index("Publish verified GitHub Release transaction")
        self.assertTrue(w92 < w94_build < w94_verify < w93)
        self.assertIn("RELEASE-CI-PROVENANCE-AUTHORIZATION.json", workflow)

    def test_w93_publisher_requires_w94_before_any_github_release_mutation(self):
        publisher = PUBLISHER.read_text(encoding="utf-8")
        handoff = publisher.index("W94_STAGE_PROVENANCE_HANDOFF")
        verify = publisher.index("verify-transaction-handoff")
        preexisting = publisher.index("W93_STAGE_PREEXISTING_RELEASE_CHECK")
        draft = publisher.index("W93_STAGE_DRAFT_CREATE")
        self.assertTrue(handoff <= verify < preexisting < draft)
        self.assertIn("test -f release/RELEASE-CI-PROVENANCE-AUTHORIZATION.json", publisher)
        self.assertIn("--transaction-script scripts/publish_release_transaction.sh", publisher)

    def test_permissions_are_scoped_by_job(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n\njobs:", workflow)
        build = workflow[workflow.index("  build-native:"):workflow.index("  publish-release:")]
        self.assertIn("contents: read", build)
        self.assertIn("id-token: write", build)
        self.assertIn("attestations: write", build)
        self.assertIn("artifact-metadata: write", build)
        publish = workflow[workflow.index("  publish-release:"):]
        self.assertIn("permissions:\n      contents: write", publish)
        self.assertNotIn("id-token: write", publish)
        self.assertNotIn("attestations: write", publish)

    def test_w94_is_handoff_only_and_w93_remains_publication_boundary(self):
        source = AUTH.read_text(encoding="utf-8")
        publisher = PUBLISHER.read_text(encoding="utf-8")
        self.assertIn('"transaction_handoff_authority": True', source)
        self.assertIn('"publication_authority": False', source)
        self.assertNotIn("gh release create", source)
        self.assertIn("gh release create", publisher)
        self.assertIn("gh release edit", publisher)
        self.assertIn("--draft=false", publisher)

    def test_external_provenance_truth_is_never_inferred_from_source(self):
        report = _module(AUDIT, "w94_external").audit(ROOT)
        external = report["external_runtime_requirements"]
        for name in (
            "github_oidc_provenance_verified_for_arm64_at_tag_runtime",
            "github_oidc_provenance_verified_for_x86_64_at_tag_runtime",
            "w94_ci_provenance_handoff_verified_at_tag_runtime",
        ):
            self.assertIn(name, external)
            self.assertFalse(external[name])
        for marker in ("physical UAT", "W91", "W92", "W93", "W94", "external runtime fact"):
            self.assertIn(marker, report["notes"])

    def test_release_boundary_and_workflow_count_stay_non_authoritative(self):
        version = VERSION.read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
