import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.service_wave71_app import AppRuntime, create_server

ROOT = Path(__file__).resolve().parents[1]


class Wave71CandidateDossierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.readiness = {"manual_scenarios": [{"id":"journey","title":"Recorrido","required":True,"view":"home","precondition":"empresa","expected":"flujo"}]}
        self.preflight = {"ready_to_begin_physical_uat": True, "checks": [{"id":"machine","status":"PASS"}], "blockers": []}
        self.evidence = {
            "current_build": {"git_sha":"a"*40,"architecture":"arm64","product_version":"0.9.0.dev1","signing_mode":"ad_hoc","notarized":False},
            "physical_uat": {"accepted_for_current_build": False},
            "release_readiness": {"stage":"BLOCKED","production_ready":False,"blocker_codes":["physical_uat_missing","development_version"]},
        }

    def tearDown(self):
        if self.runtime.social_scheduler is not None:self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown();self.runtime.transcriptions.shutdown();self.runtime.renders.shutdown();self.tmp.cleanup()

    def _dossier(self, sessions=None, preflight=None, evidence=None):
        with patch.object(self.runtime,"product_uat_readiness",return_value=self.readiness), patch.object(self.runtime,"physical_uat_preflight",return_value=preflight or self.preflight), patch.object(self.runtime,"release_evidence",return_value=evidence or self.evidence), patch.object(self.runtime.physical_uat,"list",return_value=sessions or []):
            return self.runtime.candidate_certification_dossier(self.company["id"])

    def test_ready_for_physical_uat_when_preflight_passes(self):
        row=self._dossier();self.assertEqual(row["schema"],"binario.marketing.candidate-certification-dossier.v1");self.assertEqual(row["stage"],"READY_FOR_PHYSICAL_UAT");self.assertTrue(row["safety"]["read_only"]);self.assertFalse(row["governance"]["dossier_is_release_authority"]);self.assertEqual(len(row["dossier_sha256"]),64)

    def test_active_session_takes_precedence(self):
        session={"id":"uat-1","status":"IN_PROGRESS","operator":"UAT","started_at":"2026-08-21T10:00:00Z","finished_at":None,"physical_uat_complete":False,"evidence_sha256":None,"scenarios":[{"required":True,"status":"PASS"}]}
        row=self._dossier([session]);self.assertEqual(row["stage"],"PHYSICAL_UAT_IN_PROGRESS");self.assertEqual(row["uat"]["latest_session"]["required_pass"],1)

    def test_accepted_exact_build_is_reported_but_does_not_make_production_ready(self):
        evidence=dict(self.evidence);evidence["physical_uat"]={"accepted_for_current_build":True};evidence["release_readiness"]={"stage":"BLOCKED","production_ready":False,"blocker_codes":["distribution_signing_missing","notarization_missing"]}
        row=self._dossier(evidence=evidence);self.assertEqual(row["stage"],"PHYSICAL_UAT_PASSED_FOR_BUILD");self.assertFalse(row["release"]["production_ready"]);self.assertIn("distribution_signing_missing",row["release"]["blocker_codes"])

    def test_digest_is_stable_for_same_canonical_evidence(self):
        first=self._dossier();second=self._dossier();self.assertNotEqual(first["generated_at"],second["generated_at"]);self.assertEqual(first["dossier_sha256"],second["dossier_sha256"])

    def test_http_projection_and_ui_are_read_only(self):
        server=create_server(self.runtime,"127.0.0.1",0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            base=f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base+"/release-evidence.js",timeout=5) as response: chained=response.read().decode("utf-8")
            self.assertIn("candidate-certification-dossier.js",chained);self.assertIn("data-candidate-dossier-wave71",chained)
            with urlopen(base+"/candidate-certification-dossier.js",timeout=5) as response: ui=response.read().decode("utf-8")
            self.assertIn("Expediente del candidato físico",ui)
            for forbidden in ("method:'POST'","method:'PATCH'","setInterval","sendBeacon","RELEASE_READY = True"):self.assertNotIn(forbidden,ui)
        finally:
            server.shutdown();server.server_close();thread.join(timeout=3)

    def test_release_contract_and_workflow_count_remain_non_authoritative(self):
        version=(ROOT/"src/binario_marketing/version.py").read_text(encoding="utf-8");self.assertIn('__version__ = "0.9.0"',version);self.assertIn("RELEASE_READY = True",version);self.assertIn('RELEASE_TAG: str | None = "v0.9.0"',version)
        workflows=sorted(p.name for p in (ROOT/".github/workflows").glob("*.yml"));self.assertEqual(workflows,["ci.yml","full-mac-app.yml","persistent-release.yml"])
        service=(ROOT/"src/binario_marketing/service_wave71_app.py").read_text(encoding="utf-8");self.assertNotIn("RELEASE_READY = True",service);self.assertIn("dossier_is_release_authority",service)


if __name__ == "__main__":unittest.main()
