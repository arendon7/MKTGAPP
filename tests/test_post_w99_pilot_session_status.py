from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen
from unittest import mock

from binario_marketing.service_post_w99_pilot_session_status_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotSessionStatusHTTPTests(unittest.TestCase):
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

    def test_status_is_local_minimized_and_does_not_infer_provider_readiness(self):
        with urlopen(self.root + "/api/pilot-session/status", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["schema"], "binario.marketing.pilot-session-status.v1")
        self.assertEqual(payload["backend"], {"status": "OK", "mode": "LOCAL_PILOT"})
        self.assertEqual(payload["local_data"]["total"], 4)
        self.assertEqual({row["id"] for row in payload["local_data"]["checks"]}, {"companies", "projects", "campaigns", "publications"})
        self.assertEqual(payload["snapshot"]["status"], "NONE")
        self.assertFalse(payload["snapshot"]["integrity_checked"])
        self.assertEqual(payload["safety"], {
            "provider_reads": False,
            "provider_mutations": False,
            "credentials_read": False,
            "paths_exposed": False,
            "hashes_exposed": False,
            "automatic_polling": False,
        })
        serialized = json.dumps(payload).casefold()
        for forbidden in ("data_root", "sha256", "access_token", "client_secret", "app_secret", "authorization"):
            self.assertNotIn(forbidden, serialized)

    def test_latest_snapshot_projection_reuses_data_safety_public_shape_without_integrity_scan(self):
        fake = {
            "schema": "binario.marketing.pilot-data-safety.v1",
            "count": 1,
            "snapshots": [{
                "id": "snapshot_20260913T170000Z_deadbeef",
                "created_at": "2026-09-13T17:00:00+00:00",
                "file_count": 12,
                "total_bytes": 3456,
                "restore_available": False,
            }],
            "restore_available": False,
            "credentials_included": False,
        }
        with mock.patch.object(self.runtime.pilot_data_safety, "list_snapshots", return_value=fake), mock.patch.object(self.runtime.pilot_data_safety, "verify_snapshot") as verify:
            payload = self.runtime.pilot_session_status()
        self.assertEqual(payload["snapshot"]["status"], "AVAILABLE")
        self.assertEqual(payload["snapshot"]["count"], 1)
        self.assertEqual(payload["snapshot"]["latest"]["file_count"], 12)
        self.assertFalse(payload["snapshot"]["integrity_checked"])
        verify.assert_not_called()

    def test_store_read_failure_degrades_only_local_session_projection(self):
        with mock.patch.object(self.runtime.campaigns, "list", side_effect=ValueError("damaged")):
            payload = self.runtime.pilot_session_status()
        self.assertEqual(payload["status"], "DEGRADED")
        row = next(item for item in payload["local_data"]["checks"] if item["id"] == "campaigns")
        self.assertEqual(row, {"id": "campaigns", "label": "Campañas", "status": "ERROR", "count": None})
        self.assertNotIn("damaged", json.dumps(payload))

    def test_browser_adapter_reuses_existing_pilot_authorities_without_side_effects(self):
        source = (ROOT / "web" / "pilot-session-status.js").read_text(encoding="utf-8")
        self.assertIn("Estado piloto", source)
        self.assertIn("/api/pilot-session/status", source)
        self.assertIn("pilotJourneyReport", source)
        self.assertIn("pilotJourneyShow", source)
        self.assertIn("pilotDataSafetyOpen", source)
        self.assertIn("Integridad no se recalcula automáticamente", source)
        self.assertIn("Command Center/W50", source)
        for forbidden in (
            "/api/meta/", "method:'POST'", "method:'PATCH'", "method:'DELETE'", "setInterval(",
            "MutationObserver", "localStorage", "opsShowView", "MetaGraphClient", "AIProviderClient",
            "publish-now", "data_root", "sha256",
        ):
            self.assertNotIn(forbidden, source)

    def test_http_chain_terminal_and_release_separation(self):
        with urlopen(self.root + "/pilot-data-safety.js", timeout=5) as response:
            chained = response.read().decode("utf-8")
        self.assertIn("/pilot-session-status.js", chained)
        with urlopen(self.root + "/pilot-session-status.js", timeout=5) as response:
            source = response.read().decode("utf-8")
        self.assertIn("POST_W99_PILOT_SESSION_STATUS", source)

        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_session_status_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_data_safety_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("MetaCredentialStore", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_session_status_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_SESSION_STATUS.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production", docs.casefold())
        self.assertIn("w50", docs.casefold())
        self.assertIn("no provider", docs.casefold())


if __name__ == "__main__":
    unittest.main()
