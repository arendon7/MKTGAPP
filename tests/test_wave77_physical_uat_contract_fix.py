import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from binario_marketing.service_wave76_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]


class Wave77PhysicalUATContractFixTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_current_runtime_accepts_wave69_preflight_contract(self):
        readiness = {
            "manual_scenarios": [
                {
                    "id": "journey",
                    "title": "Recorrido",
                    "required": True,
                    "view": "home",
                    "precondition": "empresa",
                    "expected": "flujo",
                }
            ]
        }
        preflight = {
            "schema": "binario.marketing.physical-uat-preflight.v1",
            "ready_to_begin_physical_uat": True,
            "checks": [{"id": "physical-machine", "status": "PASS", "passed": True}],
            "blockers": [],
        }
        evidence = {
            "current_build": {
                "git_sha": "a" * 40,
                "architecture": "arm64",
                "product_version": "0.9.0.dev1",
                "signing_mode": "ad_hoc",
                "notarized": False,
            },
            "physical_uat": {"accepted_for_current_build": False},
            "release_readiness": {
                "stage": "BLOCKED",
                "production_ready": False,
                "blocker_codes": ["physical_uat_missing", "development_version"],
            },
        }
        with (
            patch.object(self.runtime, "product_uat_readiness", return_value=readiness),
            patch.object(self.runtime, "physical_uat_preflight", return_value=preflight),
            patch.object(self.runtime, "release_evidence", return_value=evidence),
            patch.object(self.runtime.physical_uat, "list", return_value=[]),
        ):
            dossier = self.runtime.candidate_certification_dossier(self.company["id"])

        self.assertEqual(dossier["stage"], "READY_FOR_PHYSICAL_UAT")
        self.assertTrue(dossier["preflight"]["ready"])
        self.assertEqual(dossier["next_action"], "Start guided physical UAT on this exact Mac build")
        self.assertFalse(dossier["release"]["production_ready"])
        self.assertFalse(dossier["governance"]["dossier_is_release_authority"])

    def test_wave71_uses_canonical_wave69_key(self):
        service = (ROOT / "src/binario_marketing/service_wave71_app.py").read_text(encoding="utf-8")
        self.assertIn('preflight.get("ready_to_begin_physical_uat")', service)
        self.assertNotIn('preflight.get("ready_for_physical_uat")', service)


if __name__ == "__main__":
    unittest.main()
