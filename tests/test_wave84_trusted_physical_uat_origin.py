import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WRITER=ROOT/"scripts/write_physical_uat_candidate.py"


class Wave84TrustedPhysicalUATOriginTests(unittest.TestCase):
    def _fake_app(self,root:Path)->Path:
        app=root/"Binario Marketing IA.app"; resources=app/"Contents/Resources"; source=resources/"source"; package=source/"src/binario_marketing"; package.mkdir(parents=True); (source/"web").mkdir(parents=True); (source/"apps").mkdir(parents=True)
        (package/"__init__.py").write_text("",encoding="utf-8"); (package/"version.py").write_text('__version__="0.9.0.dev1"\nRELEASE_READY=False\nRELEASE_TAG=None\n',encoding="utf-8")
        (source/"web/app.js").write_text("console.log('w84');\n",encoding="utf-8"); (source/"apps/manifest.json").write_text('{"id":"fake"}\n',encoding="utf-8")
        (resources/"BUILD_PROVENANCE.json").write_text(json.dumps({"schema":"binario.marketing.full-mac-build.v4","git_sha":"a"*40,"architecture":"arm64","product_version":"0.9.0.dev1"}),encoding="utf-8")
        (resources/"RELEASE_READINESS.json").write_text(json.dumps({"schema":"binario.marketing.release-readiness.v1","git_sha":"a"*40,"production_ready":False}),encoding="utf-8")
        (resources/"launch.py").write_text("from binario_marketing.service_wave76_app import serve\n",encoding="utf-8"); return app

    @staticmethod
    def _run(app:Path,event:str,ref:str,verify=False):
        env=dict(os.environ,GITHUB_EVENT_NAME=event,GITHUB_REF=ref); cmd=[sys.executable,str(WRITER),"--app",str(app)]
        if verify: cmd.append("--verify")
        return subprocess.run(cmd,env=env,capture_output=True,text=True,check=False)

    def test_origin_roles_are_derived_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            cases=(("main","push","refs/heads/main",True),("tag","push","refs/tags/v1.0.0",True),("pr","pull_request","refs/pull/94/merge",False),("dispatch","workflow_dispatch","refs/heads/main",False),("local","local","local",False))
            for name,event,ref,trusted in cases:
                with self.subTest(name=name):
                    app=self._fake_app(root/name); proc=self._run(app,event,ref); self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
                    row=json.loads((app/"Contents/Resources/PHYSICAL_UAT_CANDIDATE.json").read_text(encoding="utf-8"))
                    self.assertEqual(row["role"],"PHYSICAL_UAT_CANDIDATE_ONLY" if trusted else "VALIDATION_BUILD_ONLY"); self.assertIs(row["build_origin"]["trusted_for_physical_uat"],trusted); self.assertIs(row["physical_uat"]["eligible_build_origin"],trusted); self.assertEqual(row["certification_guard_wave"],84)

    def test_recorded_origin_is_verified_and_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=self._fake_app(Path(tmp)); self.assertEqual(self._run(app,"push","refs/heads/main").returncode,0)
            verified=self._run(app,"local","local",verify=True); self.assertEqual(verified.returncode,0,verified.stdout+verified.stderr)
            path=app/"Contents/Resources/PHYSICAL_UAT_CANDIDATE.json"; row=json.loads(path.read_text(encoding="utf-8")); row["build_origin"]["trusted_for_physical_uat"]=False; path.write_text(json.dumps(row),encoding="utf-8")
            bad=self._run(app,"local","local",verify=True); self.assertNotEqual(bad.returncode,0); self.assertIn("build-origin trust mismatch",bad.stderr)

    def test_packager_preserves_wave83_filename_but_exposes_authoritative_role(self):
        source=(ROOT/"scripts/package_current_arm64_candidate.py").read_text(encoding="utf-8")
        self.assertIn("Binario-Marketing-IA-PHYSICAL-UAT-arm64",source)
        self.assertIn("VALIDATION_BUILD_ONLY",source); self.assertIn("physical_uat_eligible",source); self.assertIn("EXPECTED_GUARD_WAVE = 84",source); self.assertIn('DELIVERY_SCHEMA = "binario.marketing.full-mac-delivery.v3"',source)

    def test_all_physical_uat_gates_require_same_trusted_origin(self):
        collector=(ROOT/"scripts/collect_release_uat.py").read_text(encoding="utf-8"); gate=(ROOT/"scripts/release_candidate_gate.py").read_text(encoding="utf-8"); service=(ROOT/"src/binario_marketing/service_wave69_app.py").read_text(encoding="utf-8")
        for source in (collector,gate,service):
            self.assertIn("PHYSICAL_UAT_CANDIDATE_ONLY",source); self.assertIn("refs/heads/main",source); self.assertIn("refs/tags/v",source); self.assertIn("trusted_for_physical_uat",source); self.assertIn("eligible_build_origin",source)
        self.assertIn("trusted_build_origin",collector); self.assertIn("physical_uat_candidate_manifest_missing_or_invalid",gate); self.assertIn("_require_physical_uat_preflight",service)

    def test_w82_and_w83_boundaries_remain_intact(self):
        verifier=(ROOT/"scripts/verify_release_tag.py").read_text(encoding="utf-8"); self.assertIn("verify_pipeline_contract",verifier); self.assertIn("--uat-evidence",verifier); self.assertIn("--production",verifier)
        workflow=(ROOT/".github/workflows/full-mac-app.yml").read_text(encoding="utf-8"); self.assertIn("build_full_mac_current_guarded.sh --arch arm64",workflow); self.assertIn("package_current_arm64_candidate.py",workflow)
        version=(ROOT/"src/binario_marketing/version.py").read_text(encoding="utf-8"); self.assertIn("0.9.0.dev1",version); self.assertIn("RELEASE_READY = False",version); self.assertIn("RELEASE_TAG: str | None = None",version)
        workflows=sorted(path.name for path in (ROOT/".github/workflows").glob("*.yml")); self.assertEqual(workflows,["ci.yml","full-mac-app.yml","persistent-release.yml"])


if __name__=="__main__": unittest.main()
