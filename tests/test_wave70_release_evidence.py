import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.request import urlopen

from binario_marketing.release_readiness import PREPARED_RELEASE, source_release_readiness, source_release_state
from binario_marketing.service_wave70_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class Wave70ReleaseEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.build = {
            "source": "BUILD_PROVENANCE.json",
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0",
            "release_channel": "development",
            "signing_mode": "ad_hoc",
            "notarized": False,
        }
        self.machine = {
            "system": "Darwin",
            "macos_version": "15.7.7",
            "machine": "arm64",
            "is_ci": False,
            "physical_gate_eligible": True,
        }

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _passed_session(self, build=None, machine=None):
        build = dict(build or self.build)
        machine = dict(machine or self.machine)
        readiness = self.runtime.product_uat_readiness(self.company["id"])
        with patch("binario_marketing.physical_uat_store.machine_snapshot", return_value=machine):
            row = self.runtime.physical_uat.create(
                self.company["id"], scenarios=list(readiness["manual_scenarios"]), build=build, operator="UAT"
            )
        for scenario in row["scenarios"]:
            status = "PASS" if scenario["required"] else "SKIPPED"
            row = self.runtime.physical_uat.update_scenario(
                self.company["id"], row["id"], scenario["id"], {"status": status, "note": "verificado"}
            )
        return self.runtime.physical_uat.finish(
            self.company["id"], row["id"], readiness=readiness
        )

    def test_exact_build_physical_pass_satisfies_only_uat_blocker(self):
        session = self._passed_session()
        self.assertTrue(session["physical_uat_complete"])
        with patch.object(self.runtime, "_build_provenance", return_value=dict(self.build)):
            payload = self.runtime.release_evidence(self.company["id"])
        self.assertEqual(payload["schema"], "binario.marketing.release-evidence.v1")
        self.assertTrue(payload["physical_uat"]["accepted_for_current_build"])
        self.assertEqual(payload["physical_uat"]["accepted"]["session_id"], session["id"])
        blockers = payload["release_readiness"]["blocker_codes"]
        self.assertNotIn("physical_uat_missing", blockers)
        for removed_source_blocker in ("development_version", "release_flag_false", "release_tag_missing"):
            self.assertNotIn(removed_source_blocker, blockers)
        for expected in ("distribution_signing_missing", "notarization_missing"):
            self.assertIn(expected, blockers)
        self.assertFalse(payload["release_readiness"]["production_ready"])
        self.assertTrue(payload["release_boundary"]["release_ready"])
        self.assertEqual(payload["release_boundary"]["release_tag"], "v0.9.0")
        self.assertEqual(source_release_state(), PREPARED_RELEASE)

    def test_stale_git_sha_is_rejected_fail_closed(self):
        stale = dict(self.build, git_sha="b" * 40)
        self._passed_session(build=stale)
        with patch.object(self.runtime, "_build_provenance", return_value=dict(self.build)):
            payload = self.runtime.release_evidence(self.company["id"])
        latest = payload["physical_uat"]["latest_validation"]
        self.assertFalse(latest["accepted_for_current_build"])
        self.assertIn("git_sha_mismatch", latest["rejection_reasons"])
        self.assertIn("physical_uat_missing", payload["release_readiness"]["blocker_codes"])

    def test_architecture_and_version_mismatch_are_rejected(self):
        mismatched = dict(self.build, architecture="x86_64", product_version="0.9.1")
        self._passed_session(build=mismatched)
        with patch.object(self.runtime, "_build_provenance", return_value=dict(self.build)):
            payload = self.runtime.release_evidence(self.company["id"])
        reasons = payload["physical_uat"]["latest_validation"]["rejection_reasons"]
        self.assertIn("architecture_mismatch", reasons)
        self.assertIn("version_mismatch", reasons)
        self.assertFalse(payload["physical_uat"]["accepted_for_current_build"])

    def test_tampered_evidence_digest_is_rejected(self):
        session = self._passed_session()
        path = self.runtime.physical_uat._path(self.company["id"], session["id"])
        row = json.loads(path.read_text(encoding="utf-8"))
        row["operator"] = "tampered"
        path.write_text(json.dumps(row), encoding="utf-8")
        with patch.object(self.runtime, "_build_provenance", return_value=dict(self.build)):
            payload = self.runtime.release_evidence(self.company["id"])
        latest = payload["physical_uat"]["latest_validation"]
        self.assertFalse(latest["digest_valid"])
        self.assertIn("evidence_digest_mismatch", latest["rejection_reasons"])
        self.assertIn("physical_uat_missing", payload["release_readiness"]["blocker_codes"])

    def test_ci_session_never_satisfies_physical_gate(self):
        ci_machine = dict(self.machine, is_ci=True, physical_gate_eligible=False)
        session = self._passed_session(machine=ci_machine)
        self.assertFalse(session["physical_uat_complete"])
        with patch.object(self.runtime, "_build_provenance", return_value=dict(self.build)):
            payload = self.runtime.release_evidence(self.company["id"])
        latest = payload["physical_uat"]["latest_validation"]
        self.assertFalse(latest["machine_eligible"])
        self.assertIn("machine_ineligible", latest["rejection_reasons"])
        self.assertIn("physical_uat_missing", payload["release_readiness"]["blocker_codes"])

    def test_http_projection_is_get_only_and_browser_has_no_release_authority(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(base + "/physical-uat-preflight.js", timeout=5) as response:
                chained = response.read().decode("utf-8")
            self.assertIn("release-evidence.js", chained)
            self.assertIn("data-release-evidence-wave70", chained)
            with urlopen(base + "/release-evidence.js", timeout=5) as response:
                ui = response.read().decode("utf-8")
            self.assertIn("Puente UAT física → gate de release", ui)
            for forbidden in ("method:'POST'", "method:'PATCH'", "setInterval", "sendBeacon", "RELEASE_READY = True"):
                self.assertNotIn(forbidden, ui)
            with urlopen(base + f"/api/companies/{self.company['id']}/release-evidence", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertTrue(payload["safety"]["read_only"])
            self.assertFalse(payload["safety"]["release_state_mutation_performed"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_release_contract_and_workflow_count_are_prepared_not_authoritative(self):
        version = (ROOT / "src" / "binario_marketing" / "version.py").read_text(encoding="utf-8")
        self.assertIn('__version__ = "0.9.0"', version)
        self.assertIn("RELEASE_READY = True", version)
        self.assertIn('RELEASE_TAG: str | None = "v0.9.0"', version)
        source = source_release_readiness()
        self.assertTrue(source["source_ready"])
        self.assertFalse(source["operational_inputs_complete"])
        self.assertFalse(source["production_ready"])
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_wave70_app.py").read_text(encoding="utf-8")
        self.assertNotIn("RELEASE_READY = True", service)
        self.assertIn("physical_uat_can_remove_only_uat_blocker", service)


if __name__ == "__main__":
    unittest.main()
