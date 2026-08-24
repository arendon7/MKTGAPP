from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERIFY_PATH = ROOT / "scripts" / "verify_distribution_trust.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"
NOTARIZE = ROOT / "scripts" / "notarize_release_candidate.sh"
GATE = ROOT / "scripts" / "release_candidate_gate.py"
BUILDER = ROOT / "scripts" / "build_full_mac_app.sh"


def _module():
    spec = importlib.util.spec_from_file_location("wave87_distribution", VERIFY_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _digest(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


class Wave87DeveloperIDNotarizationTrustTests(unittest.TestCase):
    def _evidence(self, *, git_sha: str = "a" * 40, arch: str = "arm64") -> dict:
        core = {
            "schema": "binario.marketing.distribution-trust.v1",
            "git_sha": git_sha,
            "architecture": arch,
            "product_version": "0.9.0",
            "runtime_wave": 76,
            "signing_mode": "developer_id",
            "developer_id_identity": "Developer ID Application: Example Corp (TEAM123456)",
            "notarized": True,
            "notary_submission_id": "01234567-89ab-cdef-0123-456789abcdef",
            "notary_status": "Accepted",
            "stapler_validated": True,
            "gatekeeper_assessed": True,
            "candidate_manifest_sha256": "b" * 64,
            "release_authority": False,
        }
        return {**core, "evidence_sha256": _digest(core)}

    def test_distribution_verifier_requires_exact_sha_arch_and_notary_truth(self):
        verify = _module()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "distribution.json"
            row = self._evidence()
            path.write_text(json.dumps(row), encoding="utf-8")
            report = verify.verify(path, git_sha="a" * 40, architecture="arm64", product_version="0.9.0")
            self.assertTrue(report["notarized"])
            self.assertEqual(report["signing_mode"], "developer_id")
            self.assertFalse(report["release_authority"])
            with self.assertRaisesRegex(ValueError, "architecture mismatch"):
                verify.verify(path, git_sha="a" * 40, architecture="x86_64")
            row["gatekeeper_assessed"] = False
            path.write_text(json.dumps(row), encoding="utf-8")
            with self.assertRaises(ValueError):
                verify.verify(path, git_sha="a" * 40, architecture="arm64")

    def test_notarization_helper_is_shell_valid_and_checks_apple_trust_chain(self):
        subprocess.run(["bash", "-n", str(NOTARIZE)], check=True)
        source = NOTARIZE.read_text(encoding="utf-8")
        self.assertIn("Developer ID Application identity is required", source)
        self.assertIn("Developer\\ ID\\ Application:*", source)
        for marker in ("notarytool submit", "--wait", "stapler staple", "stapler validate", "spctl --assess", "codesign --verify"):
            self.assertIn(marker, source)
        self.assertNotIn("RELEASE_READY=True", source)

    def test_release_gate_and_embedded_bundle_include_distribution_verifier(self):
        source = GATE.read_text(encoding="utf-8")
        builder = BUILDER.read_text(encoding="utf-8")
        self.assertIn('ap.add_argument("--distribution-evidence"', source)
        self.assertIn("distribution_trust_evidence_missing", source)
        self.assertIn("from verify_distribution_trust import verify", source)
        self.assertIn('verify_distribution_trust.py" "$RELEASE_TOOLS/verify_distribution_trust.py', builder)
        self.assertIn('signing_mode = "developer_id"', source)
        self.assertIn("notarized = True", source)

    def test_tag_workflow_installs_real_credentials_notarizes_then_gates_then_packages(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        for secret in (
            "APPLE_DEVELOPER_ID_P12_BASE64",
            "APPLE_DEVELOPER_ID_P12_PASSWORD",
            "APPLE_DEVELOPER_IDENTITY",
            "APPLE_NOTARY_KEY_P8_BASE64",
            "APPLE_NOTARY_KEY_ID",
            "APPLE_NOTARY_ISSUER_ID",
        ):
            self.assertIn(f"secrets.{secret}", workflow)
        self.assertIn("security import", workflow)
        self.assertIn("BINARIO_CODESIGN_IDENTITY", workflow)
        notarize = workflow.index("notarize_release_candidate.sh")
        verify = workflow.index("verify_distribution_trust.py")
        gate = workflow.index("release_candidate_gate.py")
        package = workflow.index("Package immutable release asset")
        self.assertLess(notarize, verify)
        self.assertLess(verify, gate)
        self.assertLess(gate, package)
        window = workflow[gate:package]
        self.assertIn("--distribution-evidence", window)
        self.assertIn("--uat-evidence", window)
        self.assertIn("--production", window)

    def test_pr_certification_does_not_require_release_secrets_or_notarize(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        pr_start = workflow.index("certify-current-runtime-x86:")
        preflight = workflow.index("release-preflight:")
        pr_block = workflow[pr_start:preflight]
        self.assertNotIn("APPLE_DEVELOPER_ID_P12_BASE64", pr_block)
        self.assertNotIn("notarize_release_candidate.sh", pr_block)
        self.assertIn("Build and audit x86 current runtime", pr_block)

    def test_prepared_release_version_and_workflow_count_stay_non_authoritative(self):
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
