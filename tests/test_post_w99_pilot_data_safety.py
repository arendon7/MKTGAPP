from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest import mock

from binario_marketing.pilot_data_safety import PilotDataSafety
from binario_marketing.service_post_w99_pilot_data_safety_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotDataSafetyUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "data"
        self.root.mkdir(parents=True)
        (self.root / "companies.json").write_text('{"companies":[]}\n', encoding="utf-8")
        media = self.root / "State" / "company-media" / "company_demo"
        media.mkdir(parents=True)
        (media / "media_demo.jpg").write_bytes(b"media-bytes")
        (self.root / "temp").mkdir()
        (self.root / "temp" / "render.part").write_bytes(b"transient")
        (self.root / "logs").mkdir()
        (self.root / "logs" / "debug.log").write_text("log", encoding="utf-8")
        self.safety = PilotDataSafety(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_snapshot_copies_authoritative_files_excludes_transient_and_hides_inventory(self):
        public = self.safety.create_snapshot()
        self.assertTrue(public["verified"])
        self.assertFalse(public["restore_available"])
        self.assertNotIn("path", public)
        self.assertNotIn("sha256", public)
        snapshot = self.safety.backup_root / public["id"]
        self.assertEqual((snapshot / "data" / "companies.json").read_text(encoding="utf-8"), '{"companies":[]}\n')
        self.assertEqual((snapshot / "data" / "State" / "company-media" / "company_demo" / "media_demo.jpg").read_bytes(), b"media-bytes")
        self.assertFalse((snapshot / "data" / "temp").exists())
        self.assertFalse((snapshot / "data" / "logs").exists())
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "binario.marketing.pilot-data-snapshot.v1")
        self.assertTrue(all("sha256" in row and "path" in row for row in manifest["files"]))
        listing = self.safety.list_snapshots()
        self.assertFalse(listing["credentials_included"])
        self.assertFalse(listing["restore_available"])
        self.assertEqual(listing["count"], 1)
        self.assertNotIn("files", listing["snapshots"][0])

    def test_verification_detects_corruption(self):
        public = self.safety.create_snapshot()
        copied = self.safety.backup_root / public["id"] / "data" / "companies.json"
        copied.write_text("corrupted", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "verification failed"):
            self.safety.verify_snapshot(public["id"])

    def test_snapshot_aborts_when_source_inventory_changes(self):
        stable = self.safety._scan()
        changed = dict(stable)
        changed["later.json"] = (1, 1)
        with mock.patch.object(self.safety, "_scan", side_effect=[stable, changed]):
            with self.assertRaisesRegex(ValueError, "changed during snapshot"):
                self.safety.create_snapshot()
        self.assertEqual(list(self.safety.backup_root.glob("snapshot_*")), [])
        self.assertEqual(list(self.safety.backup_root.glob(".*.part")), [])

    def test_symlink_is_rejected(self):
        target = self.root / "companies.json"
        link = self.root / "linked.json"
        try:
            link.symlink_to(target)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        with self.assertRaisesRegex(ValueError, "symbolic link"):
            self.safety.create_snapshot()


class PilotDataSafetyHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        (self.runtime.data_root / "pilot.json").write_text('{"ok":true}\n', encoding="utf-8")
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

    def _post(self, path: str, *, operator: bool = True):
        headers = {"X-Mercadeo-Operator": "pilot-data-safety"} if operator else {}
        request = Request(self.root + path, data=b"", headers=headers, method="POST")
        return urlopen(request, timeout=10)

    def test_snapshot_mutation_requires_operator_header_and_public_api_is_minimized(self):
        with self.assertRaises(HTTPError) as caught:
            self._post("/api/pilot-data-safety/snapshots", operator=False)
        self.assertEqual(caught.exception.code, 403)
        with self._post("/api/pilot-data-safety/snapshots") as response:
            created = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 201)
        self.assertTrue(created["verified"])
        self.assertNotIn("path", created)
        self.assertNotIn("sha256", created)
        with urlopen(self.root + "/api/pilot-data-safety/snapshots", timeout=5) as response:
            listing = json.loads(response.read().decode("utf-8"))
        self.assertEqual(listing["count"], 1)
        self.assertFalse(listing["credentials_included"])
        row = listing["snapshots"][0]
        self.assertNotIn("files", row)
        with self._post(f"/api/pilot-data-safety/snapshots/{created['id']}/verify") as response:
            verified = json.loads(response.read().decode("utf-8"))
        self.assertTrue(verified["verified"])

    def test_browser_layer_is_explicit_local_and_has_no_restore_or_provider_authority(self):
        source = (ROOT / "web" / "pilot-data-safety.js").read_text(encoding="utf-8")
        self.assertIn("Respaldo local", source)
        self.assertIn("Crear snapshot verificado", source)
        self.assertIn("Verificar integridad", source)
        self.assertIn("X-Mercadeo-Operator", source)
        self.assertIn("/api/pilot-data-safety/snapshots", source)
        self.assertIn("button.addEventListener('click',async()=>{render();await refresh()})", source)
        for forbidden in (
            "/api/meta/", "setInterval(", "MutationObserver", "localStorage", "restoreSnapshot",
            "deleteSnapshot", "MetaGraphClient", "AIProviderClient", "publish-now",
        ):
            self.assertNotIn(forbidden, source)

    def test_terminal_and_release_separation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_data_safety_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_journey_smoke_app as base", service)
        self.assertIn("PilotDataSafety(runtime.data_root)", service)
        self.assertNotIn("MetaGraphClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_data_safety_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_DATA_SAFETY.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production", docs.casefold())
        self.assertIn("restore", docs.casefold())
        self.assertIn("keychain", docs.casefold())


if __name__ == "__main__":
    unittest.main()
