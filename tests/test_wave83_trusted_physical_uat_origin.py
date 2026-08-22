import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WRITER = ROOT / "scripts/write_physical_uat_candidate.py"


class Wave83TrustedPhysicalUATOriginTests(unittest.TestCase):
    def _fake_app(self, root: Path) -> Path:
        app = root / "Binario Marketing IA.app"
        resources = app / "Contents/Resources"
        source = resources / "source"
        package = source / "src/binario_marketing"
        package.mkdir(parents=True)
        (source / "web").mkdir(parents=True)
        (source / "apps").mkdir(parents=True)
        (package / "__init__.py").write_text("", encoding="utf-8")
        (package / "version.py").write_text('__version__="0.9.0.dev1"\nRELEASE_READY=False\nRELEASE_TAG=None\n', encoding="utf-8")
        (source / "web/app.js").write_text("console.log('w83');\n", encoding="utf-8")
        (source / "apps/manifest.json").write_text('{"id":"fake"}\n', encoding="utf-8")
        (resources / "BUILD_PROVENANCE.json").write_text(json.dumps({"schema":"binario.marketing.full-mac-build.v4","git_sha":"a"*40,"architecture":"arm64","product_version":"0.9.0.dev1"}), encoding="utf-8")
        (resources / "RELEASE_READINESS.json").write_text(json.dumps({"schema":"binario.marketing.release-readiness.v1","git_sha":"a"*40,"production_ready":False}), encoding="utf-8")
        (resources / "launch.py").write_text("from binario_marketing.service_wave76_app import serve\n", encoding="utf-8")
        return app

    @staticmethod
    def _run(app: Path, event: str, ref: str, verify=False):
        env=dict(os.environ,GITHUB_EVENT_NAME=event,GITHUB_REF=ref)
        cmd=[sys.executable,str(WRITER),"--app",str(app)]
        if verify: cmd.append("--verify")
        return subprocess.run(cmd,env=env,capture_output=True,text=True,check=False)

    def test_main_and_version_tag_are_trusted_but_pr_is_validation_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name,event,ref,trusted in (
                ("main","push","refs/heads/main",True),
                ("tag","push","refs/tags/v1.0.0",True),
                ("pr","pull_request","refs/pull/91/merge",False),
                ("dispatch","workflow_dispatch","refs/heads/main",False),
            ):
                app=self._fake_app(root/name)
                proc=self._run(app,event,ref)
                self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                row=json.loads((app/"Contents/Resources/PHYSICAL_UAT_CANDIDATE.json").read_text(encoding="utf-8"))
                self.assertEqual(row["role"],"PHYSICAL_UAT_CANDIDATE_ONLY" if trusted else "VALIDATION_BUILD_ONLY")
                self.assertIs(row["build_origin"]["trusted_for_physical_uat"],trusted)
                self.assertIs(row["physical_uat"]["eligible_build_origin"],trusted)
                self.assertEqual(row["certification_guard_wave"],83)

    def test_verification_uses_recorded_origin_and_detects_tampering(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=self._fake_app(Path(tmp))
            self.assertEqual(self._run(app,"push","refs/heads/main").returncode,0)
            verified=self._run(app,"local","local",verify=True)
            self.assertEqual(verified.returncode,0,verified.stdout+verified.stderr)
            path=app/"Contents/Resources/PHYSICAL_UAT_CANDIDATE.json"
            row=json.loads(path.read_text(encoding="utf-8")); row["build_origin"]["trusted_for_physical_uat"]=False
            path.write_text(json.dumps(row),encoding="utf-8")
            bad=self._run(app,"local","local",verify=True)
            self.assertNotEqual(bad.returncode,0)
            self.assertIn("build-origin trust mismatch",bad.stderr)

    def test_all_uat_gates_require_trusted_origin(self):
        collector=(ROOT/"scripts/collect_release_uat.py").read_text(encoding="utf-8")
        gate=(ROOT/"scripts/release_candidate_gate.py").read_text(encoding="utf-8")
        service=(ROOT/"src/binario_marketing/service_wave69_app.py").read_text(encoding="utf-8")
        for source in (collector,gate,service):
            self.assertIn("PHYSICAL_UAT_CANDIDATE_ONLY",source)
            self.assertIn("refs/heads/main",source)
            self.assertIn("refs/tags/v",source)
            self.assertIn("trusted_for_physical_uat",source)
            self.assertIn("eligible_build_origin",source)
        self.assertIn("trusted_build_origin",collector)
        self.assertIn("physical_uat_candidate_manifest_missing_or_invalid",gate)
        self.assertIn("_require_physical_uat_preflight",service)

    def test_builder_runs_w81_then_w83_and_w82_hard_stop_remains(self):
        builder=(ROOT/"scripts/build_full_mac_current_guarded.sh").read_text(encoding="utf-8")
        self.assertIn("audit_wave81_physical_uat_candidate_handoff.sh",builder)
        self.assertIn("audit_wave83_trusted_physical_uat_origin.sh",builder)
        self.assertLess(builder.index("audit_wave81_physical_uat_candidate_handoff.sh"),builder.index("audit_wave83_trusted_physical_uat_origin.sh"))
        verifier=(ROOT/"scripts/verify_release_tag.py").read_text(encoding="utf-8")
        self.assertIn("verify_pipeline_contract",verifier)
        self.assertIn("--uat-evidence",verifier)
        self.assertIn("--production",verifier)
        version=(ROOT/"src/binario_marketing/version.py").read_text(encoding="utf-8")
        self.assertIn("0.9.0.dev1",version); self.assertIn("RELEASE_READY = False",version); self.assertIn("RELEASE_TAG: str | None = None",version)
        workflows=sorted(path.name for path in (ROOT/".github/workflows").glob("*.yml")); self.assertEqual(workflows,["ci.yml","full-mac-app.yml","persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
