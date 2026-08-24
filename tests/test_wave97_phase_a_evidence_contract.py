from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from binario_marketing.physical_uat_store import PhysicalUATStore, REQUIRED_PHASE_A_IDS, machine_snapshot
from binario_marketing.service_wave70_app import _evidence_digest, _session_validation

FINALIZER = ROOT / "scripts/finalize_physical_uat.py"


def _finalizer_module():
    spec = importlib.util.spec_from_file_location("w97_phase_a_finalizer", FINALIZER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _scenarios(ids: set[str]) -> list[dict]:
    return [{"id": scenario_id, "label": scenario_id} for scenario_id in sorted(ids)]


def _session(ids: set[str]) -> dict:
    rows = [
        {
            "id": scenario_id,
            "required": True,
            "status": "PASS",
            "note": "observed",
            "updated_at": "2026-08-24T03:00:00+00:00",
        }
        for scenario_id in sorted(ids)
    ]
    session = {
        "schema": "binario.marketing.physical-uat-session.v1",
        "id": "uat_" + "1" * 24,
        "company_id": "company_" + "2" * 24,
        "status": "PASSED",
        "created_at": "2026-08-24T02:50:00+00:00",
        "updated_at": "2026-08-24T03:00:00+00:00",
        "finished_at": "2026-08-24T03:00:00+00:00",
        "machine": {
            "system": "Darwin",
            "machine": "arm64",
            "is_ci": False,
            "physical_gate_eligible": True,
        },
        "build": {
            "source": "BUILD_PROVENANCE.json",
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0",
        },
        "scenarios": rows,
        "physical_uat_complete": True,
        "evidence_sha256": None,
    }
    session["evidence_sha256"] = _evidence_digest(session)
    return session


class Wave97PhaseAEvidenceContractTests(unittest.TestCase):
    def test_generic_ci_env_is_never_physical_gate_eligible(self):
        with patch.dict(os.environ, {"CI": "true"}, clear=True), \
             patch("binario_marketing.physical_uat_store.platform.system", return_value="Darwin"), \
             patch("binario_marketing.physical_uat_store.platform.machine", return_value="arm64"), \
             patch("binario_marketing.physical_uat_store.platform.mac_ver", return_value=("15.7", ("", "", ""), "")):
            snapshot = machine_snapshot()
        self.assertTrue(snapshot["is_ci"])
        self.assertFalse(snapshot["physical_gate_eligible"])

    def test_store_rejects_reduced_required_scenario_contract(self):
        reduced = set(REQUIRED_PHASE_A_IDS) - {"results-decision"}
        with tempfile.TemporaryDirectory() as raw:
            store = PhysicalUATStore(Path(raw))
            with self.assertRaisesRegex(ValueError, "required scenario set drift"):
                store.create(
                    "company_" + "1" * 24,
                    scenarios=_scenarios(reduced),
                    build={"git_sha": "a" * 40},
                    operator="QA",
                )

    def test_release_evidence_rejects_reduced_required_scenario_set(self):
        reduced = set(REQUIRED_PHASE_A_IDS) - {"results-decision"}
        session = _session(reduced)
        current_build = {
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0",
        }
        result = _session_validation(session, current_build)
        self.assertFalse(result["required_scenario_set_exact"])
        self.assertFalse(result["accepted_for_current_build"])
        self.assertIn("required_scenario_set_drift", result["rejection_reasons"])

    def test_finalizer_rejects_reduced_phase_a_even_with_valid_digest(self):
        module = _finalizer_module()
        reduced = set(REQUIRED_PHASE_A_IDS) - {"results-decision"}
        session = _session(reduced)
        report = {
            "schema": module.PHASE_A_SCHEMA,
            "session": session,
            "summary": {
                "required": len(reduced),
                "passed": len(reduced),
                "failed": 0,
                "blocked": 0,
                "pending": 0,
                "physical_uat_complete": True,
            },
            "release_authority": False,
        }
        candidate = {"git_sha": "a" * 40, "product_version": "0.9.0"}
        with self.assertRaisesRegex(ValueError, "required scenario set drift"):
            module._phase_a(report, candidate)

    def test_canonical_five_scenarios_remain_accepted(self):
        session = _session(set(REQUIRED_PHASE_A_IDS))
        current_build = {
            "git_sha": "a" * 40,
            "architecture": "arm64",
            "product_version": "0.9.0",
        }
        result = _session_validation(session, current_build)
        self.assertTrue(result["required_scenario_set_exact"])
        self.assertTrue(result["accepted_for_current_build"])

        module = _finalizer_module()
        report = {
            "schema": module.PHASE_A_SCHEMA,
            "session": session,
            "summary": {
                "required": 5,
                "passed": 5,
                "failed": 0,
                "blocked": 0,
                "pending": 0,
                "physical_uat_complete": True,
            },
            "release_authority": False,
        }
        candidate = {"git_sha": "a" * 40, "product_version": "0.9.0"}
        phase_a = module._phase_a(report, candidate)
        self.assertEqual(phase_a["required_scenarios"], 5)
        self.assertEqual(phase_a["passed_scenarios"], 5)


if __name__ == "__main__":
    unittest.main()
