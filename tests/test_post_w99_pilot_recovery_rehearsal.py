from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing.pilot_data_safety import PilotDataSafety
from binario_marketing.pilot_recovery_rehearsal import PilotRecoveryRehearsal
from binario_marketing.service_post_w99_pilot_recovery_rehearsal_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PilotRecoveryRehearsalUnitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "data"
        self.root.mkdir(parents=True)
        (self.root / "companies.json").write_text('{"companies":[{"id":"demo"}]}\n', encoding="utf-8")
        (self.root / "events.jsonl").write_text('{"event":"one"}\n{"event":"two"}\n', encoding="utf-8")
        (self.root / "media.bin").write_bytes(b"pilot-media")
        database = self.root / "pilot.sqlite"
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE pilot (id INTEGER PRIMARY KEY, value TEXT)")
            connection.execute("INSERT INTO pilot(value) VALUES ('ready')")
            connection.commit()
        finally:
            connection.close()
        self.safety = PilotDataSafety(self.root)
        self.rehearsal = PilotRecoveryRehearsal(self.root, self.safety)

    def tearDown(self):
        self.tmp.cleanup()

    def test_verified_snapshot_rehearses_in_isolation_and_leaves_active_data_identical(self):
        active_before = {path.name: _digest(path) for path in self.root.iterdir() if path.is_file()}
        snapshot = self.safety.create_snapshot()
        result = self.rehearsal.rehearse(snapshot["id"])
        active_after = {path.name: _digest(path) for path in self.root.iterdir() if path.is_file()}

        self.assertEqual(result["schema"], "binario.marketing.pilot-recovery-rehearsal.v1")
        self.assertEqual(result["status"], "PASS")
        self.assertTrue(result["verified_source"])
        self.assertTrue(result["copied_to_isolated_workspace"])
        self.assertTrue(result["isolated_copy_verified"])
        self.assertTrue(result["active_data_unchanged"])
        self.assertTrue(result["workspace_cleaned"])
        self.assertFalse(result["restore_performed"])
        self.assertFalse(result["delete_performed"])
        self.assertFalse(result["provider_reads"])
        self.assertFalse(result["provider_mutations"])
        self.assertFalse(result["workers_started"])
        self.assertEqual(result["readability"]["files_checked"], 4)
        self.assertEqual(result["readability"]["structured_files_checked"], 3)
        self.assertEqual(result["readability"]["json_documents"], 1)
        self.assertEqual(result["readability"]["jsonl_documents"], 2)
        self.assertEqual(result["readability"]["sqlite_databases"], 1)
        self.assertEqual(active_before, active_after)
        self.assertFalse(self.rehearsal.rehearsal_root.exists())

        public = json.dumps(result, sort_keys=True)
        self.assertNotIn("sha256", public)
        self.assertNotIn(str(self.root), public)
        self.assertNotIn(str(self.safety.backup_root), public)

    def test_structurally_invalid_snapshot_fails_closed_and_cleans_workspace(self):
        broken = self.root / "broken.json"
        broken.write_text("{not-json", encoding="utf-8")
        active_digest = _digest(broken)
        snapshot = self.safety.create_snapshot()

        with self.assertRaisesRegex(ValueError, "structurally readable"):
            self.rehearsal.rehearse(snapshot["id"])

        self.assertEqual(_digest(broken), active_digest)
        self.assertFalse(self.rehearsal.rehearsal_root.exists())

    def test_snapshot_root_symlink_is_rejected_before_rehearsal(self):
        snapshot = self.safety.create_snapshot()
        root = self.safety.backup_root / snapshot["id"]
        real = self.safety.backup_root / "held_snapshot_data"
        root.rename(real)
        try:
            root.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            real.rename(root)
            self.skipTest("symlinks unavailable")

        with self.assertRaisesRegex(ValueError, "root cannot be a symbolic link"):
            self.rehearsal.rehearse(snapshot["id"])
        self.assertFalse(self.rehearsal.rehearsal_root.exists())


class PilotRecoveryRehearsalHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        (self.runtime.data_root / "pilot-recovery.json").write_text('{"ok":true}\n', encoding="utf-8")
        self.snapshot = self.runtime.pilot_data_safety.create_snapshot()
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
        return urlopen(request, timeout=15)

    def test_rehearsal_requires_explicit_operator_and_returns_minimized_evidence(self):
        path = f"/api/pilot-data-safety/snapshots/{self.snapshot['id']}/rehearse"
        with self.assertRaises(HTTPError) as caught:
            self._post(path, operator=False)
        self.assertEqual(caught.exception.code, 403)

        with self._post(path) as response:
            payload = json.loads(response.read().decode("utf-8"))
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["status"], "PASS")
        self.assertTrue(payload["active_data_unchanged"])
        self.assertTrue(payload["workspace_cleaned"])
        self.assertFalse(payload["restore_performed"])
        serialized = json.dumps(payload, sort_keys=True)
        self.assertNotIn("sha256", serialized)
        self.assertNotIn(str(self.runtime.data_root), serialized)

    def test_http_chain_loads_rehearsal_after_language_polish(self):
        with urlopen(self.root + "/pilot-language-polish.js", timeout=5) as response:
            chained = response.read().decode("utf-8")
        self.assertIn("/pilot-recovery-rehearsal.js", chained)
        with urlopen(self.root + "/pilot-recovery-rehearsal.js", timeout=5) as response:
            source = response.read().decode("utf-8")
        self.assertIn("POST_W99_PILOT_RECOVERY_REHEARSAL", source)
        self.assertIn("Probar recuperación", source)
        self.assertIn("datos activos sin cambios", source)

    def test_browser_action_is_explicit_and_has_no_provider_restore_delete_or_polling_authority(self):
        source = (ROOT / "web" / "pilot-recovery-rehearsal.js").read_text(encoding="utf-8")
        self.assertIn("X-Mercadeo-Operator", source)
        self.assertIn("/api/pilot-data-safety/snapshots", source)
        self.assertIn("method==='POST'", source)
        self.assertIn("Probar recuperación", source)
        for forbidden in (
            "/api/meta/", "setInterval(", "MutationObserver", "localStorage", "restoreSnapshot",
            "deleteSnapshot", "MetaGraphClient", "AIProviderClient", "publish-now", "opsShowView",
        ):
            self.assertNotIn(forbidden, source)

    def test_terminal_release_separation_and_documentation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])

        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_recovery_rehearsal_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_language_polish_app as base", service)
        self.assertIn("pilot_recovery_rehearsal.rehearse", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)

        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_recovery_rehearsal_app", dev)

        docs = (ROOT / "docs" / "POST_W99_PILOT_RECOVERY_REHEARSAL.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production", docs.casefold())
        self.assertIn("does **not** provide", docs)
        self.assertIn("live restore", docs.casefold())
        self.assertIn("provider reads", docs.casefold())


if __name__ == "__main__":
    unittest.main()
