from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.version import RELEASE_READY, RELEASE_TAG, __version__

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "audit_wave96_prepared_release_source.py"
VERSION = ROOT / "src" / "binario_marketing" / "version.py"
WORKFLOW = ROOT / ".github" / "workflows" / "persistent-release.yml"


def _module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Wave96PrepareReleaseSourceTests(unittest.TestCase):
    def test_canonical_source_is_exact_prepared_v0_9_0(self):
        self.assertEqual(__version__, "0.9.0")
        self.assertTrue(RELEASE_READY)
        self.assertEqual(RELEASE_TAG, "v0.9.0")
        self.assertEqual(source_release_state(), PREPARED_RELEASE)

    def test_prepared_source_still_has_zero_operational_authority(self):
        report = source_release_readiness()
        self.assertTrue(report["source_ready"])
        self.assertEqual(report["stage"], "SOURCE_CONTRACT_READY")
        self.assertFalse(report["operational_inputs_complete"])
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["blocker_codes"], [])

    def test_wave96_audit_is_read_only_and_prepared_for_physical_uat(self):
        report = _module(AUDIT, "w96_audit").audit(ROOT)
        self.assertEqual(report["schema"], "binario.marketing.prepared-release-source-audit.v1")
        self.assertEqual(report["certification_guard_wave"], 96)
        self.assertEqual(report["source_contract_wave"], 95)
        self.assertEqual(report["runtime_wave"], 76)
        self.assertEqual(report["status"], "PREPARED_FOR_PHYSICAL_UAT")
        self.assertEqual(report["failure_codes"], [])
        self.assertTrue(all(report["checks"].values()), report)
        self.assertTrue(report["physical_uat_required"])
        self.assertFalse(report["operational_authorization"])
        self.assertFalse(report["release_authority"])
        self.assertFalse(report["publication_authority"])
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["mutations_performed"])

    def test_wave96_audit_cli_passes_without_mutating_source(self):
        before = VERSION.read_bytes()
        proc = subprocess.run(
            [sys.executable, str(AUDIT), "--repo", str(ROOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        after = VERSION.read_bytes()
        self.assertEqual(proc.returncode, 0, proc.stdout + "\n" + proc.stderr)
        self.assertIn('"status": "PREPARED_FOR_PHYSICAL_UAT"', proc.stdout)
        self.assertEqual(before, after)

    def test_canonical_tag_verifier_accepts_intent_but_not_runtime_evidence(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_release_tag.py"), "--tag", "v0.9.0"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("RELEASE TAG PASS: v0.9.0", proc.stdout)
        source = (ROOT / "scripts" / "verify_release_tag.py").read_text(encoding="utf-8")
        self.assertNotIn("physical_uat_attestation_verified = True", source)
        self.assertNotIn("publication_authority = True", source)

    def test_persistent_release_still_requires_external_evidence_before_packaging(self):
        workflow = WORKFLOW.read_text(encoding="utf-8")
        uat = workflow.index("Decode and verify exact physical UAT attestation")
        gate = workflow.index("Enforce and persist production release candidate gate")
        package = workflow.index("Package immutable release asset")
        self.assertLess(uat, gate)
        self.assertLess(gate, package)
        self.assertIn("--expected-source-release-state PREPARED_RELEASE", workflow[uat:gate])
        self.assertIn('--expected-release-tag "$GITHUB_REF_NAME"', workflow[uat:gate])
        self.assertIn("--production", workflow[gate:package])
        self.assertIn("--uat-evidence", workflow[gate:package])
        self.assertIn("--distribution-evidence", workflow[gate:package])

    def test_exact_physical_candidate_remains_main_push_only(self):
        source = (ROOT / "scripts" / "write_physical_uat_candidate.py").read_text(encoding="utf-8")
        self.assertIn('event == "push"', source)
        self.assertIn('ref == "refs/heads/main"', source)
        self.assertIn("SOURCE_CONTRACT_WAVE = 95", source)
        self.assertIn("PREPARED_RELEASE", source)

    def test_release_architecture_and_workflow_count_are_preserved(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        audit = (ROOT / "scripts" / "release_enablement_audit.py").read_text(encoding="utf-8")
        for marker in ("W91", "W92", "W93", "W94", "W95"):
            self.assertIn(marker, audit)


if __name__ == "__main__":
    unittest.main()
