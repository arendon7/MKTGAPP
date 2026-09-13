from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.pilot_daily_receipt import PilotDailyReceiptStore, PilotDailyReceiptStoreCorrupt
from binario_marketing.service_post_w99_pilot_daily_receipt_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"
CHECK_IDS = ["runtime", "companies", "journey", "snapshot", "recovery"]


def gate(*, ready: bool = True) -> dict:
    checks = [{"id": check_id, "pass": ready or check_id != "recovery"} for check_id in CHECK_IDS]
    passed = sum(1 for row in checks if row["pass"])
    return {
        "schema": "binario.marketing.pilot-launch-gate.v1",
        "ready": passed == 5,
        "passed": passed,
        "total": 5,
        "checks": checks,
        "journey": {"mode": "PORTFOLIO", "pass": 10, "total": 10, "ready": True},
    }


class PilotDailyReceiptUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "State" / "pilot" / "daily_receipts.json"
        self.store = PilotDailyReceiptStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_record_is_minimized_append_only_and_summary_is_day_based(self):
        first = self.store.record({"local_date": "2026-09-13", "gate": gate(ready=True)})
        second = self.store.record({"local_date": "2026-09-13", "gate": gate(ready=False)})
        third = self.store.record({"local_date": "2026-09-14", "gate": gate(ready=True)})
        self.assertNotEqual(first["id"], second["id"])
        self.assertNotEqual(second["id"], third["id"])
        listing = self.store.list()
        self.assertEqual(listing["summary"]["receipt_count"], 3)
        self.assertEqual(listing["summary"]["days_observed"], 2)
        self.assertEqual(listing["summary"]["ready_days"], 1)
        self.assertEqual(listing["summary"]["attention_days"], 1)
        self.assertFalse(listing["safety"]["free_text_stored"])
        self.assertFalse(listing["safety"]["identity_fields_stored"])
        serialized = json.dumps(listing, sort_keys=True)
        for forbidden in ("company_id", "contact_id", "provider_id", "path", "sha256", "token", "note"):
            self.assertNotIn(forbidden, serialized)

    def test_payload_rejects_free_text_unknown_fields_and_inconsistent_gate(self):
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            self.store.record({"local_date": "2026-09-13", "gate": gate(), "note": "do not store me"})
        inconsistent = gate()
        inconsistent["ready"] = False
        with self.assertRaisesRegex(ValueError, "internally inconsistent"):
            self.store.record({"local_date": "2026-09-13", "gate": inconsistent})
        reordered = gate()
        reordered["checks"] = list(reversed(reordered["checks"]))
        with self.assertRaisesRegex(ValueError, "order"):
            self.store.record({"local_date": "2026-09-13", "gate": reordered})

    def test_corrupt_or_symlink_ledger_fails_closed_without_overwrite(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"broken":', encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaises(PilotDailyReceiptStoreCorrupt):
            self.store.list()
        with self.assertRaises(PilotDailyReceiptStoreCorrupt):
            self.store.record({"local_date": "2026-09-13", "gate": gate()})
        self.assertEqual(self.path.read_bytes(), before)


class PilotDailyReceiptHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _post(self, payload: dict, *, operator: bool = True):
        headers = {"Content-Type": "application/json"}
        if operator:
            headers["X-Mercadeo-Operator"] = "pilot-daily-receipt"
        request = Request(
            self.root + "/api/pilot/daily-receipts",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        return urlopen(request, timeout=10)

    def test_daily_receipt_requires_explicit_operator_action_and_history_is_minimized(self):
        payload = {"local_date": "2026-09-13", "gate": gate()}
        with self.assertRaises(HTTPError) as caught:
            self._post(payload, operator=False)
        self.assertEqual(caught.exception.code, 403)
        with self._post(payload) as response:
            created = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 201)
        self.assertTrue(created["gate"]["ready"])
        with urlopen(self.root + "/api/pilot/daily-receipts?limit=30", timeout=5) as response:
            listing = json.loads(response.read().decode("utf-8"))
        self.assertEqual(listing["summary"]["days_observed"], 1)
        self.assertEqual(len(listing["receipts"]), 1)
        self.assertFalse(listing["safety"]["execution_authority"])
        serialized = json.dumps(listing, sort_keys=True)
        for forbidden in ("company_id", "contact_id", "provider_id", "sha256", "credential"):
            self.assertNotIn(forbidden, serialized)

    def test_corrupt_ledger_returns_500_and_is_not_replaced(self):
        path = self.runtime.pilot_daily_receipts.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"broken":', encoding="utf-8")
        before = path.read_bytes()
        with self.assertRaises(HTTPError) as caught:
            urlopen(self.root + "/api/pilot/daily-receipts", timeout=5)
        self.assertEqual(caught.exception.code, 500)
        with self.assertRaises(HTTPError) as caught:
            self._post({"local_date": "2026-09-13", "gate": gate()})
        self.assertEqual(caught.exception.code, 500)
        self.assertEqual(path.read_bytes(), before)

    def test_browser_layer_is_explicit_and_contains_no_free_text_or_provider_authority(self):
        source = (ROOT / "web" / "pilot-daily-receipt.js").read_text(encoding="utf-8")
        gate_source = (ROOT / "web" / "pilot-launch-gate.js").read_text(encoding="utf-8")
        self.assertIn("Cerrar jornada", source)
        self.assertIn("Historial del piloto", source)
        self.assertIn("X-Mercadeo-Operator", source)
        self.assertIn("/api/pilot/daily-receipts", source)
        self.assertIn("post-w99-pilot-launch-gate-rendered", gate_source)
        self.assertIn("pilotLaunchGateClose", gate_source)
        for forbidden in (
            "textarea", "localStorage", "sessionStorage", "setInterval(", "MutationObserver",
            "/api/meta/", "MetaGraphClient", "AIProviderClient", "publish-now", "restoreSnapshot",
        ):
            self.assertNotIn(forbidden, source)

    def test_terminal_and_release_separation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_daily_receipt_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_launch_gate_app as base", service)
        self.assertIn("PilotDailyReceiptStore", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_daily_receipt_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_DAILY_RECEIPT.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production", docs.casefold())
        self.assertIn("append-only", docs.casefold())
        self.assertIn("free-form", docs.casefold())
        self.assertIn("snapshot", docs.casefold())


if __name__ == "__main__":
    unittest.main()
