from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.pilot_incident_log import PilotIncidentLog, PilotIncidentLogCorrupt
from binario_marketing.service_post_w99_pilot_incident_log_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


def incident_payload(*, severity: str = "HIGH") -> dict:
    return {
        "local_date": "2026-09-13",
        "module": "INBOX",
        "category": "WORKFLOW",
        "severity": severity,
    }


class PilotIncidentLogUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "State" / "pilot" / "incidents.json"
        self.store = PilotIncidentLog(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_open_and_resolution_are_append_only_structured_events(self):
        opened = self.store.open(incident_payload(severity="BLOCKING"))
        self.assertEqual(opened["status"], "OPEN")
        self.assertEqual(opened["module"], "INBOX")
        self.assertEqual(opened["severity"], "BLOCKING")
        raw_before = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(raw_before["events"]), 1)
        self.assertEqual(raw_before["events"][0]["type"], "OPENED")

        resolved = self.store.resolve(opened["id"], {"local_date": "2026-09-14"})
        self.assertEqual(resolved["status"], "RESOLVED")
        raw_after = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(raw_after["events"]), 2)
        self.assertEqual(raw_after["events"][0], raw_before["events"][0])
        self.assertEqual(raw_after["events"][1]["type"], "RESOLVED")
        with self.assertRaisesRegex(ValueError, "already resolved"):
            self.store.resolve(opened["id"], {"local_date": "2026-09-14"})

    def test_summary_and_filters_are_derived_without_sensitive_fields(self):
        high = self.store.open(incident_payload(severity="HIGH"))
        blocking = self.store.open({**incident_payload(severity="BLOCKING"), "module": "BACKUP", "category": "RECOVERY"})
        low = self.store.open({**incident_payload(severity="LOW"), "module": "CONTENT", "category": "UI"})
        self.store.resolve(low["id"], {"local_date": "2026-09-13"})
        listing = self.store.list()
        self.assertEqual(listing["summary"], {
            "incident_count": 3,
            "open_count": 2,
            "resolved_count": 1,
            "blocking_open": 1,
            "high_open": 1,
        })
        self.assertEqual({row["id"] for row in self.store.list(status="OPEN")["incidents"]}, {high["id"], blocking["id"]})
        self.assertEqual([row["id"] for row in self.store.list(status="RESOLVED")["incidents"]], [low["id"]])
        self.assertFalse(listing["safety"]["free_text_stored"])
        self.assertFalse(listing["safety"]["identity_fields_stored"])
        serialized = json.dumps(listing, sort_keys=True)
        for forbidden in ("company_id", "contact_id", "provider_id", "path", "sha256", "token", "note", "message_text"):
            self.assertNotIn(forbidden, serialized)

    def test_free_text_unknown_enums_and_delete_semantics_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            self.store.open({**incident_payload(), "note": "free text is forbidden"})
        with self.assertRaisesRegex(ValueError, "module"):
            self.store.open({**incident_payload(), "module": "OTHER"})
        with self.assertRaisesRegex(ValueError, "category"):
            self.store.open({**incident_payload(), "category": "UNKNOWN"})
        with self.assertRaisesRegex(ValueError, "severity"):
            self.store.open({**incident_payload(), "severity": "CRITICAL"})
        self.assertFalse(hasattr(self.store, "delete"))

    @unittest.skipIf(os.name == "nt", "symlink behavior differs on Windows runners")
    def test_corrupt_or_symlink_store_fails_closed_without_overwrite(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text('{"broken":', encoding="utf-8")
        before = self.path.read_bytes()
        with self.assertRaises(PilotIncidentLogCorrupt):
            self.store.list()
        with self.assertRaises(PilotIncidentLogCorrupt):
            self.store.open(incident_payload())
        self.assertEqual(self.path.read_bytes(), before)

        self.path.unlink()
        target = self.path.parent / "target.json"
        target.write_text(json.dumps({"schema": "binario.marketing.pilot-incidents.v1", "events": []}), encoding="utf-8")
        self.path.symlink_to(target)
        with self.assertRaises(PilotIncidentLogCorrupt):
            self.store.list()


class PilotIncidentLogHTTPTests(unittest.TestCase):
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

    def _post(self, path: str, payload: dict, *, operator: bool = True):
        headers = {"Content-Type": "application/json"}
        if operator:
            headers["X-Mercadeo-Operator"] = "pilot-incident-log"
        request = Request(self.root + path, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
        return urlopen(request, timeout=10)

    def test_http_requires_explicit_operator_and_resolves_exact_incident(self):
        with self.assertRaises(HTTPError) as caught:
            self._post("/api/pilot/incidents", incident_payload(), operator=False)
        self.assertEqual(caught.exception.code, 403)
        with self._post("/api/pilot/incidents", incident_payload()) as response:
            opened = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 201)
        self.assertEqual(opened["status"], "OPEN")
        with self._post(f"/api/pilot/incidents/{opened['id']}/resolve", {"local_date": "2026-09-13"}) as response:
            resolved = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(resolved["status"], "RESOLVED")
        with urlopen(self.root + "/api/pilot/incidents?status=ALL&limit=100", timeout=5) as response:
            listing = json.loads(response.read().decode("utf-8"))
        self.assertEqual(listing["summary"]["resolved_count"], 1)
        self.assertEqual(listing["summary"]["open_count"], 0)

    def test_http_has_no_delete_or_free_text_escape_hatch(self):
        with self.assertRaises(HTTPError) as caught:
            self._post("/api/pilot/incidents", {**incident_payload(), "description": "must fail"})
        self.assertEqual(caught.exception.code, 400)
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_incident_log_app.py").read_text(encoding="utf-8")
        self.assertNotIn("def do_DELETE", source)
        self.assertNotIn("MetaGraphClient", source)
        self.assertNotIn("AIProviderClient", source)

    def test_browser_is_select_only_explicit_and_provider_free(self):
        source = (ROOT / "web" / "pilot-incident-log.js").read_text(encoding="utf-8")
        self.assertIn("Registrar incidencia", source)
        self.assertIn("Marcar resuelta", source)
        self.assertIn("select", source)
        self.assertIn("X-Mercadeo-Operator", source)
        self.assertIn("post-w99-pilot-launch-gate-rendered", source)
        for forbidden in (
            "textarea", "contenteditable", "localStorage", "sessionStorage", "setInterval(",
            "MutationObserver", "/api/meta/", "MetaGraphClient", "AIProviderClient",
            "publish-now", "restoreSnapshot", "createSnapshot", "method:'DELETE'",
        ):
            self.assertNotIn(forbidden, source)

    def test_static_chain_terminal_and_release_boundaries(self):
        with urlopen(self.root + "/pilot-month-tracker.js", timeout=5) as response:
            parent = response.read().decode("utf-8")
        self.assertIn("/pilot-incident-log.js", parent)
        with urlopen(self.root + "/pilot-incident-log.js", timeout=5) as response:
            incident_js = response.read().decode("utf-8")
        self.assertIn("Registrar incidencia", incident_js)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_month_tracker_app", dev)
        self.assertIn("service_post_w99_pilot_incident_log_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_INCIDENT_LOG.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production readiness", docs.casefold())
        self.assertIn("append-only", docs.casefold())
        self.assertIn("no free-form", docs.casefold())


if __name__ == "__main__":
    unittest.main()
