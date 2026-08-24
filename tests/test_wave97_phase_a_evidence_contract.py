from __future__ import annotations

import importlib.util
import json
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

from binario_marketing.physical_uat_store import (
    CANONICAL_PHASE_A_IDS,
    OPTIONAL_PHASE_A_IDS,
    PhysicalUATStore,
    REQUIRED_PHASE_A_IDS,
    machine_snapshot,
)
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


def _session(required_ids: set[str], *, optional: bool = True, extra_optional: str | None = None) -> dict:
    rows = [
        {
            "id": scenario_id,
            "required": True,
            "status": "PASS",
            "note": "observed",
            "updated_at": "2026-08-24T03:00:00+00:00",
        }
        for scenario_id in sorted(required_ids)
    ]
    if optional:
        rows.append({
            "id": "optional-ai",
            "required": False,
            "status": "SKIPPED",
            "note": "optional and nonblocking",
            "updated_at": "2026-08-24T03:00:00+00:00",
        })
    if extra_optional:
        rows.append({
            "id": extra_optional,
            "required": False,
            "status": "SKIPPED",
            "note": "unexpected optional row",
            "updated_at": "2026-08-24T03:00:00+00:00",
        })
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


def _report(module, session: dict) -> dict:
    required = [row for row in session["scenarios"] if row.get("required")]
    return {
        "schema": module.PHASE_A_SCHEMA,
        "session": session,
        "summary": {
            "required": len(required),
            "required_scenario_ids": sorted(REQUIRED_PHASE_A_IDS),
            "optional_scenario_ids": sorted(OPTIONAL_PHASE_A_IDS),
            "passed": sum(1 for row in required if row.get("status") == "PASS"),
            "failed": 0,
            "blocked": 0,
            "pending": 0,
            "physical_uat_complete": True,
        },
        "release_authority": False,
    }


class Wave97PhaseAEvidenceContractTests(unittest.TestCase):
    def test_generic_ci_env_is_never_physical_gate_eligible(self):
        with patch.dict(os.environ, {"CI": "true"}, clear=True), \
             patch("binario_marketing.physical_uat_store.platform.system", return_value="Darwin"), \
             patch("binario_marketing.physical_uat_store.platform.machine", return_value="arm64"), \
             patch("binario_marketing.physical_uat_store.platform.mac_ver", return_value=("15.7", ("", "", ""), "")):
            snapshot = machine_snapshot()
        self.assertTrue(snapshot["is_ci"])
        self.assertFalse(snapshot["physical_gate_eligible"])

    def test_store_accepts_only_canonical_six_rows_and_marks_optional_ai_nonrequired(self):
        with tempfile.TemporaryDirectory() as raw:
            store = PhysicalUATStore(Path(raw))
            row = store.create(
                "company_" + "1" * 24,
                scenarios=_scenarios(set(CANONICAL_PHASE_A_IDS)),
                build={"git_sha": "a" * 40},
                operator="QA",
            )
            self.assertEqual({item["id"] for item in row["scenarios"]}, CANONICAL_PHASE_A_IDS)
            required = {item["id"] for item in row["scenarios"] if item["required"]}
            optional = {item["id"] for item in row["scenarios"] if not item["required"]}
            self.assertEqual(required, REQUIRED_PHASE_A_IDS)
            self.assertEqual(optional, OPTIONAL_PHASE_A_IDS)

    def test_store_rejects_reduced_or_unexpected_scenario_contract(self):
        reduced = set(CANONICAL_PHASE_A_IDS) - {"results-decision"}
        unexpected = set(CANONICAL_PHASE_A_IDS) | {"surprise-optional"}
        for ids in (reduced, unexpected):
            with self.subTest(ids=ids), tempfile.TemporaryDirectory() as raw:
                store = PhysicalUATStore(Path(raw))
                with self.assertRaises(ValueError):
                    store.create(
                        "company_" + "1" * 24,
                        scenarios=_scenarios(ids),
                        build={"git_sha": "a" * 40},
                        operator="QA",
                    )

    def test_store_rejects_tampered_persisted_contract_before_release_evidence_can_read_it(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            store = PhysicalUATStore(root)
            company_id = "company_" + "1" * 24
            row = store.create(
                company_id,
                scenarios=_scenarios(set(CANONICAL_PHASE_A_IDS)),
                build={"git_sha": "a" * 40},
                operator="QA",
            )
            path = root / company_id / f"{row['id']}.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["scenarios"].append({
                "id": "surprise-optional",
                "required": False,
                "status": "SKIPPED",
                "note": "tampered",
                "updated_at": None,
            })
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unexpected physical UAT scenario id"):
                store.get(company_id, row["id"])

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
        candidate = {"git_sha": "a" * 40, "product_version": "0.9.0"}
        with self.assertRaisesRegex(ValueError, "scenario contract drift|scenario count drift"):
            module._phase_a(_report(module, session), candidate)

    def test_finalizer_rejects_unexpected_optional_row_even_with_recomputed_evidence_digest(self):
        module = _finalizer_module()
        session = _session(set(REQUIRED_PHASE_A_IDS), extra_optional="surprise-optional")
        candidate = {"git_sha": "a" * 40, "product_version": "0.9.0"}
        with self.assertRaisesRegex(ValueError, "scenario count drift|scenario contract drift"):
            module._phase_a(_report(module, session), candidate)

    def test_finalizer_rejects_duplicate_required_id_even_if_five_required_rows_remain(self):
        module = _finalizer_module()
        session = _session(set(REQUIRED_PHASE_A_IDS))
        required_rows = [row for row in session["scenarios"] if row["required"]]
        required_rows[-1]["id"] = required_rows[0]["id"]
        session["evidence_sha256"] = _evidence_digest(session)
        candidate = {"git_sha": "a" * 40, "product_version": "0.9.0"}
        with self.assertRaisesRegex(ValueError, "duplicates|scenario contract drift"):
            module._phase_a(_report(module, session), candidate)

    def test_canonical_five_required_plus_optional_ai_are_accepted_and_bound(self):
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
        candidate = {"git_sha": "a" * 40, "product_version": "0.9.0"}
        phase_a = module._phase_a(_report(module, session), candidate)
        self.assertEqual(phase_a["required_scenarios"], 5)
        self.assertEqual(phase_a["passed_scenarios"], 5)
        self.assertEqual(set(phase_a["required_scenario_ids"]), REQUIRED_PHASE_A_IDS)
        self.assertEqual(set(phase_a["optional_scenario_ids"]), OPTIONAL_PHASE_A_IDS)


if __name__ == "__main__":
    unittest.main()
