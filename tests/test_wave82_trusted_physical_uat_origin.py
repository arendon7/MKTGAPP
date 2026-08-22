import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "scripts" / "write_physical_uat_candidate.py"


class Wave82TrustedPhysicalUATOriginTests(unittest.TestCase):
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
        (source / "web" / "app.js").write_text("console.log('w82');\n", encoding="utf-8")
        (source / "apps" / "manifest.json").write_text('{"id":"fake"}\n', encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({
            "schema": "binario.marketing.full-mac-build.v4",
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0.dev1",
        }), encoding="utf-8")
        (resources / "RELEASE_READINESS.json").write_text(json.dumps({
            "schema": "binario.marketing.release-readiness.v1",
            "git_sha": "a" * 40,
            "production_ready": False,
        }), encoding="utf-8")
        (resources / "launch.py").write_text(
            "from binario_marketing.service_wave76_app import serve\n",
            encoding="utf-8",
        )
        return app

    @staticmethod
    def _run_writer(app: Path, *, event: str, ref: str, verify: bool = False):
        env = dict(os.environ, GITHUB_EVENT_NAME=event, GITHUB_REF=ref)
        cmd = [sys.executable, str(WRITER), "--app", str(app)]
        if verify:
            cmd.append("--verify")
        return subprocess.run(cmd, env=env, capture_output=True, text=True, check=False)

    def test_main_and_version_tag_are_physical_candidates_but_pr_is_validation_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, ref in (("main", "refs/heads/main"), ("tag", "refs/tags/v0.9.0")):
                app = self._fake_app(root / name)
                proc = self._run_writer(app, event="push", ref=ref)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                manifest = json.loads((app / "Contents/Resources/PHYSICAL_UAT_CANDIDATE.json").read_text(encoding="utf-8"))
                self.assertEqual(manifest["role"], "PHYSICAL_UAT_CANDIDATE_ONLY")
                self.assertTrue(manifest["build_origin"]["trusted_for_physical_uat"])
                self.assertTrue(manifest["physical_uat"]["eligible_build_origin"])

            pr_app = self._fake_app(root / "pr")
            pr = self._run_writer(pr_app, event="pull_request", ref="refs/pull/88/merge")
            self.assertEqual(pr.returncode, 0, pr.stdout + pr.stderr)
            pr_manifest = json.loads((pr_app / "Contents/Resources/PHYSICAL_UAT_CANDIDATE.json").read_text(encoding="utf-8"))
            self.assertEqual(pr_manifest["role"], "VALIDATION_BUILD_ONLY")
            self.assertFalse(pr_manifest["build_origin"]["trusted_for_physical_uat"])
            self.assertFalse(pr_manifest["physical_uat"]["eligible_build_origin"])

    def test_verification_uses_signed_recorded_origin_not_current_environment(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._fake_app(Path(tmp))
            written = self._run_writer(app, event="push", ref="refs/heads/main")
            self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
            verified = self._run_writer(app, event="local", ref="local", verify=True)
            self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
            row = json.loads(verified.stdout)
            self.assertEqual(row["role"], "PHYSICAL_UAT_CANDIDATE_ONLY")
            self.assertEqual(row["build_origin"]["ref"], "refs/heads/main")

    def test_tampered_origin_trust_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._fake_app(Path(tmp))
            written = self._run_writer(app, event="pull_request", ref="refs/pull/88/merge")
            self.assertEqual(written.returncode, 0, written.stdout + written.stderr)
            path = app / "Contents/Resources/PHYSICAL_UAT_CANDIDATE.json"
            row = json.loads(path.read_text(encoding="utf-8"))
            row["build_origin"]["trusted_for_physical_uat"] = True
            path.write_text(json.dumps(row), encoding="utf-8")
            verified = self._run_writer(app, event="local", ref="local", verify=True)
            self.assertNotEqual(verified.returncode, 0)
            self.assertIn("build-origin trust mismatch", verified.stderr)

    def test_release_uat_and_release_gate_require_trusted_origin(self):
        collector = (ROOT / "scripts/collect_release_uat.py").read_text(encoding="utf-8")
        gate = (ROOT / "scripts/release_candidate_gate.py").read_text(encoding="utf-8")
        for source in (collector, gate):
            self.assertIn('"PHYSICAL_UAT_CANDIDATE_ONLY"', source)
            self.assertIn('"refs/heads/main"', source)
            self.assertIn('"refs/tags/v"', source)
            self.assertIn('"trusted_for_physical_uat"', source)
            self.assertIn('"eligible_build_origin"', source)
        self.assertIn('"trusted_build_origin"', collector)
        self.assertIn("physical_uat_candidate_manifest_missing_or_invalid", gate)

    def test_in_app_uat_mutations_are_preflight_gated(self):
        service = (ROOT / "src/binario_marketing/service_wave69_app.py").read_text(encoding="utf-8")
        self.assertIn('"trusted-main-candidate"', service)
        self.assertIn('"PHYSICAL_UAT_CANDIDATE_ONLY"', service)
        self.assertIn('"refs/heads/main"', service)
        self.assertIn('"refs/tags/v"', service)
        self.assertIn("def _require_physical_uat_preflight", service)
        self.assertGreaterEqual(service.count("self._require_physical_uat_preflight(company_id)"), 3)

    def test_current_builder_runs_w81_then_w82_and_release_stays_closed(self):
        builder = (ROOT / "scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        self.assertIn("audit_wave81_physical_uat_candidate_handoff.sh", builder)
        self.assertIn("CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 81", builder)
        self.assertIn("audit_wave82_trusted_physical_uat_origin.sh", builder)
        self.assertIn("CURRENT ARM64 CERTIFICATION GUARD PASS: Wave 82", builder)
        version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn('0.9.0.dev1', version)
        self.assertIn("RELEASE_READY = False", version)
        self.assertIn("RELEASE_TAG: str | None = None", version)
        current = (ROOT / "scripts/build_full_mac_current.sh").read_text(encoding="utf-8")
        self.assertIn("service_wave76_app import serve", current)
        self.assertNotIn("service_wave82_app import serve", current)
        workflows = sorted(path.name for path in (ROOT / ".github/workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
