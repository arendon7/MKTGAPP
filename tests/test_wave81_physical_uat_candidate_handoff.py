import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Wave81PhysicalUATCandidateHandoffTests(unittest.TestCase):
    def _fake_app(self, root: Path) -> Path:
        app = root / "Binario Marketing IA.app"
        resources = app / "Contents" / "Resources"
        source = resources / "source"
        package = source / "src" / "binario_marketing"
        package.mkdir(parents=True)
        (source / "web").mkdir(parents=True)
        (source / "apps").mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "version.py").write_text(
            '__version__="0.9.0.dev1"\nRELEASE_READY=False\nRELEASE_TAG=None\n',
            encoding="utf-8",
        )
        (source / "web" / "app.js").write_text("console.log('w81');\n", encoding="utf-8")
        (source / "apps" / "manifest.json").write_text('{"id":"fake"}\n', encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(
            json.dumps(
                {
                    "schema": "binario.marketing.full-mac-build.v4",
                    "git_sha": "a" * 40,
                    "architecture": "arm64",
                    "product_version": "0.9.0.dev1",
                }
            ),
            encoding="utf-8",
        )
        (resources / "RELEASE_READINESS.json").write_text(
            json.dumps(
                {
                    "schema": "binario.marketing.release-readiness.v1",
                    "git_sha": "a" * 40,
                    "production_ready": False,
                }
            ),
            encoding="utf-8",
        )
        (resources / "launch.py").write_text(
            "from binario_marketing.service_wave76_app import serve\n",
            encoding="utf-8",
        )
        return app

    def test_writer_creates_exact_fail_closed_candidate_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._fake_app(Path(tmp))
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts/write_physical_uat_candidate.py"), "--app", str(app)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            manifest = json.loads((app / "Contents/Resources/PHYSICAL_UAT_CANDIDATE.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["runtime_wave"], 76)
            self.assertEqual(manifest["architecture"], "arm64")
            self.assertEqual(len(manifest["candidate_source_sha256"]), 64)
            self.assertFalse(manifest["release_boundary"]["release_ready"])
            self.assertFalse(manifest["physical_uat"]["automatic_pass"])
            self.assertFalse(manifest["sandbox_boundary"]["functional_sandbox_is_release_evidence"])

            verify = subprocess.run(
                [sys.executable, str(ROOT / "scripts/write_physical_uat_candidate.py"), "--app", str(app), "--verify"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(verify.returncode, 0, verify.stdout + verify.stderr)

    def test_manifest_verification_detects_source_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._fake_app(Path(tmp))
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/write_physical_uat_candidate.py"), "--app", str(app)],
                check=True,
                capture_output=True,
                text=True,
            )
            source_file = app / "Contents/Resources/source/web/app.js"
            source_file.write_text("console.log('tampered');\n", encoding="utf-8")
            verify = subprocess.run(
                [sys.executable, str(ROOT / "scripts/write_physical_uat_candidate.py"), "--app", str(app), "--verify"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(verify.returncode, 0)
            self.assertIn("manifest drift", verify.stderr)

    def test_release_uat_collection_requires_physical_arm64_non_ci_candidate(self):
        source = (ROOT / "scripts/collect_release_uat.py").read_text(encoding="utf-8")
        self.assertIn('provenance.get("architecture") == "arm64"', source)
        self.assertIn('host_system == "Darwin"', source)
        self.assertIn('host_machine == "arm64"', source)
        self.assertIn('not is_ci', source)
        self.assertIn('PHYSICAL_UAT_CANDIDATE.json', source)
        self.assertIn('candidate_source_sha256', source)
        self.assertIn('candidate_manifest_sha256', source)

    def test_manual_evidence_and_release_gate_require_exact_candidate_digests(self):
        recorder = (ROOT / "scripts/record_release_uat.py").read_text(encoding="utf-8")
        gate = (ROOT / "scripts/release_candidate_gate.py").read_text(encoding="utf-8")
        self.assertIn("candidate_source_sha256", recorder)
        self.assertIn("candidate_manifest_sha256", recorder)
        self.assertIn("manual UAT note must contain concrete evidence", recorder)
        self.assertIn("physical_uat_candidate_source_mismatch", gate)
        self.assertIn("physical_uat_candidate_manifest_mismatch", gate)
        self.assertIn("physical_uat_candidate_manifest_missing_or_invalid", gate)

    def test_arm64_builder_embeds_resigns_and_audits_candidate_handoff(self):
        builder = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        self.assertIn("write_physical_uat_candidate.py", builder)
        self.assertIn("codesign --force --deep", builder)
        self.assertIn("audit_wave81_physical_uat_candidate_handoff.sh", builder)
        self.assertIn("CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 81", builder)


if __name__ == "__main__":
    unittest.main()
