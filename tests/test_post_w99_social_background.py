import json
import os
import plistlib
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from binario_marketing.social_background import (
    LAUNCH_AGENT_INTERVAL_SECONDS,
    LAUNCH_AGENT_LABEL,
    install_social_background,
    run_social_background_once,
    social_background_status,
    uninstall_social_background,
)
from binario_marketing.social_process_lock import SocialProcessLock
from binario_marketing.social_store import SocialStore


class FakeMeta:
    def __init__(self):
        self.calls = []

    def publish_page_feed(self, target_id, message, link_url=None):
        self.calls.append((target_id, message, link_url))
        return "page-1_900"


class FakeLaunchctl:
    def __init__(self):
        self.loaded = False
        self.calls = []

    def __call__(self, args):
        self.calls.append(list(args))
        command = args[0]
        if command == "bootout":
            self.loaded = False
            return subprocess.CompletedProcess(args, 0, "", "")
        if command == "bootstrap":
            self.loaded = True
            return subprocess.CompletedProcess(args, 0, "", "")
        if command == "kickstart":
            return subprocess.CompletedProcess(args, 0, "", "")
        if command == "print":
            return subprocess.CompletedProcess(args, 0 if self.loaded else 113, "", "")
        raise AssertionError(f"unexpected launchctl command: {args}")


class SocialBackgroundWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "data"
        self.env = patch.dict(os.environ, {"BINARIO_IA_HOME": str(self.home)}, clear=True)
        self.env.start()
        self.store = SocialStore(self.home / "State" / "social")

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _queued(self, message="Background publish"):
        return self.store.create(
            "project-1",
            {
                "channel": "facebook_page",
                "target_id": "page-1",
                "kind": "text",
                "message": message,
                "scheduled_for": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
            },
        )

    def test_worker_publishes_due_queue_and_writes_status_outside_social_store(self):
        row = self._queued()
        fake = FakeMeta()
        with patch(
            "binario_marketing.social_background.MetaGraphClient.diagnose_env",
            return_value=SimpleNamespace(configured=True),
        ), patch(
            "binario_marketing.social_background.MetaGraphClient.from_env",
            return_value=fake,
        ):
            result = run_social_background_once()

        self.assertEqual(result.status, "OK")
        self.assertEqual(result.processed, 1)
        self.assertEqual(result.published, 1)
        self.assertEqual(self.store.get(row.id).status, "PUBLISHED")
        self.assertEqual(len(fake.calls), 1)
        status_path = self.home / "State" / "social-background" / "status.json"
        self.assertTrue(status_path.is_file())
        self.assertEqual(json.loads(status_path.read_text(encoding="utf-8"))["published"], 1)
        self.assertEqual([item.id for item in self.store.list()], [row.id])

    def test_worker_fails_closed_when_desktop_process_owns_publication_queue(self):
        row = self._queued()
        owner = SocialProcessLock(self.store.root)
        self.assertTrue(owner.acquire())
        try:
            with patch(
                "binario_marketing.social_background.MetaGraphClient.diagnose_env",
                return_value=SimpleNamespace(configured=True),
            ):
                result = run_social_background_once()
        finally:
            owner.release()
        self.assertEqual(result.status, "BUSY")
        self.assertTrue(result.busy)
        self.assertEqual(self.store.get(row.id).status, "QUEUED")
        self.assertEqual(self.store.get(row.id).attempts, 0)

    def test_worker_recovers_crashed_publish_only_after_obtaining_process_lock(self):
        row = self._queued("Interrupted")
        self.store.transition(row.id, "PUBLISHING")
        with patch(
            "binario_marketing.social_background.MetaGraphClient.diagnose_env",
            return_value=SimpleNamespace(configured=True),
        ), patch(
            "binario_marketing.social_background.MetaGraphClient.from_env",
            return_value=FakeMeta(),
        ):
            result = run_social_background_once()
        self.assertEqual(result.status, "OK")
        self.assertEqual(result.recovered, 1)
        current = self.store.get(row.id)
        self.assertEqual(current.status, "FAILED")
        self.assertIn("review remote state before retry", current.error)

    def test_worker_no_credentials_is_safe_noop(self):
        row = self._queued()
        with patch(
            "binario_marketing.social_background.MetaGraphClient.diagnose_env",
            return_value=SimpleNamespace(configured=False),
        ):
            result = run_social_background_once()
        self.assertEqual(result.status, "NO_CREDENTIALS")
        self.assertEqual(self.store.get(row.id).status, "QUEUED")


class SocialBackgroundLaunchAgentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.fake_home = Path(self.tmp.name) / "home"
        self.app = Path(self.tmp.name) / "Binario Marketing IA.app"
        resources = self.app / "Contents" / "Resources"
        python = resources / "runtime" / "python" / "bin" / "python3"
        source = resources / "source" / "src" / "binario_marketing" / "social_background.py"
        helper = self.app / "Contents" / "MacOS" / "binario-meta-keychain"
        for path in (python, source, helper):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("stub", encoding="utf-8")
        os.chmod(python, 0o755)
        os.chmod(helper, 0o755)
        self.launchctl = FakeLaunchctl()
        self.home_patch = patch("binario_marketing.social_background.Path.home", return_value=self.fake_home)
        self.platform_patch = patch("binario_marketing.social_background.platform.system", return_value="Darwin")
        self.home_patch.start()
        self.platform_patch.start()

    def tearDown(self):
        self.platform_patch.stop()
        self.home_patch.stop()
        self.tmp.cleanup()

    def test_install_is_explicit_secret_free_and_loaded_then_uninstall_is_clean(self):
        installed = install_social_background(self.app, runner=self.launchctl)
        self.assertTrue(installed.installed)
        self.assertTrue(installed.loaded)
        self.assertFalse(installed.stale)
        plist_path = self.fake_home / "Library" / "LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"
        payload = plistlib.loads(plist_path.read_bytes())
        self.assertEqual(payload["StartInterval"], LAUNCH_AGENT_INTERVAL_SECONDS)
        self.assertTrue(payload["RunAtLoad"])
        self.assertEqual(payload["ProcessType"], "Background")
        self.assertNotIn("META_ACCESS_TOKEN", payload["EnvironmentVariables"])
        self.assertTrue(payload["EnvironmentVariables"]["BINARIO_META_KEYCHAIN_HELPER"].endswith("binario-meta-keychain"))
        self.assertIn("-I", payload["ProgramArguments"])
        self.assertIn("-B", payload["ProgramArguments"])
        self.assertTrue((self.fake_home / "Library" / "Application Support" / "Binario Marketing IA" / "social-worker.py").is_file())
        self.assertTrue(any(call[0] == "bootstrap" for call in self.launchctl.calls))

        removed = uninstall_social_background(runner=self.launchctl)
        self.assertFalse(removed.installed)
        self.assertFalse(removed.loaded)
        self.assertFalse(plist_path.exists())

    def test_status_detects_stale_app_reference_without_mutation(self):
        install_social_background(self.app, runner=self.launchctl)
        python = self.app / "Contents" / "Resources" / "runtime" / "python" / "bin" / "python3"
        python.unlink()
        before = len(self.launchctl.calls)
        status = social_background_status(runner=self.launchctl)
        self.assertTrue(status.installed)
        self.assertTrue(status.stale)
        self.assertEqual(len(self.launchctl.calls), before + 1)
        self.assertEqual(self.launchctl.calls[-1][0], "print")


if __name__ == "__main__":
    unittest.main()
