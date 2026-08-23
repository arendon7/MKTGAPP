from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "release_enablement_audit.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"
AUTH = ROOT / "scripts" / "release_ci_provenance_authorization.py"
VERSION = ROOT / "src" / "binario_marketing" / "version.py"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class Wave93ReleaseEnablementAuditTests(unittest.TestCase):
    def test_source_audit_advances_to_guard_93_but_remains_fail_closed(self):
        report = _module(AUDIT, "w93_audit").audit(ROOT)
        self.assertEqual(report["schema"], "binario.marketing.release-enablement-audit.v5")
        self.assertEqual(report["runtime_wave"], 76)
        self.assertEqual(report["certification_guard_wave"], 93)
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["operational_authorization"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["publication_authority"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["mutations_performed"])

    def test_all_w93_structural_gates_are_present(self):
        report = _module(AUDIT, "w93_structure").audit(ROOT)
        missing = [name for name, ok in report["structural_gates"].items() if ok is not True]
        self.assertEqual(missing, [], report)
        for name in (
            "w93_provenance_action_pinned",
            "w93_provenance_uses_exact_packaged_path",
            "w93_sigstore_bundle_persisted",
            "w93_attestation_after_roundtrip_before_upload",
            "w93_build_job_has_oidc_attestation_permissions",
            "w93_global_permissions_are_read_only",
            "w93_publish_job_contents_write_is_scoped",
            "w93_ci_provenance_authorization_schema",
            "w93_uses_github_oidc_and_slsa",
            "w93_denies_self_hosted_attestations",
            "w93_binds_repo_workflow_ref_and_digest",
            "w93_authorization_after_w92",
            "w93_final_authorization_verification_before_publish",
            "w93_final_manifest_required_for_publish",
        ):
            self.assertTrue(report["structural_gates"][name], name)

    def test_attestation_is_after_roundtrip_and_before_native_artifact_upload(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        package = workflow.index("Package immutable release asset")
        roundtrip = workflow.index("Verify W92 packaged artifact round-trip trust")
        attest = workflow.index("Attest exact release ZIP with GitHub OIDC provenance")
        upload = workflow.index("uses: actions/upload-artifact@v4", attest)
        self.assertLess(package, roundtrip)
        self.assertLess(roundtrip, attest)
        self.assertLess(attest, upload)
        self.assertIn("subject-path: ${{ steps.package.outputs.zip_path }}", workflow)
        self.assertIn("steps.attest.outputs.bundle-path", workflow)

    def test_w93_is_the_last_authority_before_publication(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        w91 = workflow.index("Verify final W91 release authorization")
        w92 = workflow.index("Verify W92 final publication authorization")
        w93_build = workflow.index("Build W93 CI provenance publication authorization")
        w93_verify = workflow.index("Verify final W93 CI provenance authorization")
        publish = workflow.index("Publish permanent GitHub Release")
        self.assertLess(w91, w92)
        self.assertLess(w92, w93_build)
        self.assertLess(w93_build, w93_verify)
        self.assertLess(w93_verify, publish)
        self.assertIn("test -f release/RELEASE-CI-PROVENANCE-AUTHORIZATION.json", workflow)

    def test_permissions_are_least_privilege_by_job(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read\n\njobs:", workflow)
        build = workflow[workflow.index("  build-native:"):workflow.index("  publish-release:")]
        self.assertIn("id-token: write", build)
        self.assertIn("attestations: write", build)
        self.assertIn("artifact-metadata: write", build)
        publish = workflow[workflow.index("  publish-release:"):]
        self.assertIn("permissions:\n      contents: write", publish)
        self.assertNotIn("id-token: write", publish)
        self.assertNotIn("attestations: write", publish)

    def test_external_provenance_truth_is_never_inferred_from_source(self):
        report = _module(AUDIT, "w93_external").audit(ROOT)
        external = report["external_runtime_requirements"]
        for name in (
            "github_oidc_provenance_verified_for_arm64_at_tag_runtime",
            "github_oidc_provenance_verified_for_x86_64_at_tag_runtime",
            "w93_ci_provenance_publication_authorization_verified_at_tag_runtime",
        ):
            self.assertIn(name, external)
            self.assertFalse(external[name])
        self.assertIn("W91", report["notes"])
        self.assertIn("W92", report["notes"])
        self.assertIn("W93", report["notes"])
        self.assertIn("GitHub OIDC", report["notes"])

    def test_authorizer_has_no_publication_side_effect_and_release_boundary_stays_closed(self):
        source = AUTH.read_text(encoding="utf-8")
        version = VERSION.read_text(encoding="utf-8")
        self.assertNotIn("gh release create", source)
        self.assertIn('"publication_performed": False', source)
        self.assertIn('"mutations_performed": False', source)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
