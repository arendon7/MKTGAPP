import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service_wave69_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave69PhysicalUATPreflightTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.data_root=Path(self.tmp.name)/"data"; self.runtime=AppRuntime.create(ROOT,self.data_root); self.company=self.runtime.create_company({"name":"Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None: self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    @staticmethod
    def _eligible_machine(): return {"system":"Darwin","macos_version":"15.7.7","machine":"arm64","is_ci":False,"physical_gate_eligible":True}

    def _fake_packaged_runtime(self,*,trusted=True):
        resources=Path(self.tmp.name)/"Bundle/Contents/Resources"; source=resources/"source"; source.mkdir(parents=True); runtime=resources/"runtime"
        for path in (runtime/"python/bin/python3",runtime/"media/bin/ffmpeg",runtime/"media/bin/ffprobe",runtime/"transcription/bin/whisper-cli"):
            path.parent.mkdir(parents=True,exist_ok=True); path.write_text("stub",encoding="utf-8"); path.chmod(0o755)
        manifest=runtime/"transcription/RUNTIME.json"; manifest.parent.mkdir(parents=True,exist_ok=True); manifest.write_text(json.dumps({"engine":"whisper.cpp"}),encoding="utf-8")
        model=runtime/"transcription/models/ggml-tiny.bin"; model.parent.mkdir(parents=True,exist_ok=True); model.write_bytes(b"model")
        (resources/"BUILD_PROVENANCE.json").write_text(json.dumps({"git_sha":"a"*40,"architecture":"arm64","product_version":"0.9.0.dev1","release_channel":"development","signing_mode":"ad_hoc","notarized":False}),encoding="utf-8")
        candidate={
            "schema":"binario.marketing.physical-uat-candidate.v1",
            "role":"PHYSICAL_UAT_CANDIDATE_ONLY" if trusted else "VALIDATION_BUILD_ONLY",
            "git_sha":"a"*40,"architecture":"arm64","product_version":"0.9.0.dev1",
            "runtime_wave":76,"certification_guard_wave":84,"source_contract_wave":95,
            "source_release_state":"LOCKED_SOURCE","candidate_source_sha256":"b"*64,
            "build_origin":{"event":"push" if trusted else "pull_request","ref":"refs/heads/main" if trusted else "refs/pull/106/merge","trusted_for_physical_uat":trusted},
            "release_boundary":{"source_release_state":"LOCKED_SOURCE","release_ready":False,"release_tag":None,"operational_authorization":False,"release_authority":False,"publication_authority":False,"production_ready":False},
            "physical_uat":{"required":True,"automatic_pass":False,"eligible_build_origin":trusted},
        }
        (resources/"PHYSICAL_UAT_CANDIDATE.json").write_text(json.dumps(candidate),encoding="utf-8")
        self.runtime.repo_root=source; return resources

    def test_source_checkout_is_not_misreported_as_physical_bundle_ready(self):
        with patch("binario_marketing.service_wave69_app.machine_snapshot",return_value=self._eligible_machine()): payload=self.runtime.physical_uat_preflight(self.company["id"])
        self.assertFalse(payload["ready_to_begin_physical_uat"]); self.assertIn("certified-build-provenance",payload["blockers"]); self.assertIn("trusted-build-candidate",payload["blockers"]); self.assertIn("embedded-runtime",payload["blockers"])

    def test_trusted_packaged_arm64_runtime_can_pass_preflight(self):
        self._fake_packaged_runtime()
        with patch("binario_marketing.service_wave69_app.machine_snapshot",return_value=self._eligible_machine()): payload=self.runtime.physical_uat_preflight(self.company["id"])
        self.assertTrue(payload["ready_to_begin_physical_uat"]); self.assertEqual(payload["blockers"],[]); self.assertTrue(payload["candidate"]["trusted_for_physical_uat"]); self.assertEqual(payload["candidate"]["source_release_state"],"LOCKED_SOURCE"); self.assertEqual(payload["candidate"]["source_contract_wave"],95); self.assertEqual(payload["next_action"]["code"],"START_PHYSICAL_UAT")

    def test_validation_pr_bundle_cannot_start_physical_uat(self):
        self._fake_packaged_runtime(trusted=False); machine=self._eligible_machine()
        with patch("binario_marketing.service_wave69_app.machine_snapshot",return_value=machine):
            payload=self.runtime.physical_uat_preflight(self.company["id"]); self.assertFalse(payload["ready_to_begin_physical_uat"]); self.assertIn("trusted-build-candidate",payload["blockers"]); self.assertEqual(payload["candidate"]["role"],"VALIDATION_BUILD_ONLY")
            with self.assertRaisesRegex(ValueError,"trusted-build-candidate"): self.runtime.start_physical_uat(self.company["id"],{"operator":"UAT"})
        self.assertEqual(self.runtime.physical_uat.list(self.company["id"]),[])

    def test_ci_is_ineligible_even_with_complete_trusted_bundle(self):
        self._fake_packaged_runtime(); machine=dict(self._eligible_machine(),is_ci=True,physical_gate_eligible=False)
        with patch("binario_marketing.service_wave69_app.machine_snapshot",return_value=machine): payload=self.runtime.physical_uat_preflight(self.company["id"])
        self.assertFalse(payload["ready_to_begin_physical_uat"]); self.assertEqual(payload["blockers"],["physical-machine"])

    def test_active_session_requires_preflight_and_stays_manual(self):
        self._fake_packaged_runtime(); machine=self._eligible_machine()
        with patch("binario_marketing.service_wave69_app.machine_snapshot",return_value=machine), patch("binario_marketing.physical_uat_store.machine_snapshot",return_value=machine):
            session=self.runtime.start_physical_uat(self.company["id"],{"operator":"UAT"}); payload=self.runtime.physical_uat_preflight(self.company["id"])
        self.assertEqual(payload["active_session_id"],session["id"]); self.assertEqual(payload["next_action"]["code"],"CONTINUE_SESSION"); self.assertFalse(payload["safety"]["physical_uat_result_recorded"])

    def test_http_preflight_remains_read_only(self):
        server=create_server(self.runtime,"127.0.0.1",0); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base+"/guided-physical-uat.js",timeout=5) as response: guided=response.read().decode("utf-8")
            self.assertIn("physical-uat-preflight.js",guided)
            with urlopen(base+f"/api/companies/{self.company['id']}/physical-uat/preflight",timeout=5) as response: payload=json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"],"binario.marketing.physical-uat-preflight.v1"); self.assertFalse(payload["safety"]["marketing_mutation_performed"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_release_contract_remains_fail_closed(self):
        workflows=sorted(path.name for path in (ROOT/".github/workflows").glob("*.yml")); self.assertEqual(workflows,["ci.yml","full-mac-app.yml","persistent-release.yml"])
        version=(ROOT/"src/binario_marketing/version.py").read_text(encoding="utf-8"); self.assertIn("0.9.0.dev1",version); self.assertIn("RELEASE_READY = False",version); self.assertIn("RELEASE_TAG: str | None = None",version)


if __name__=="__main__": unittest.main()
