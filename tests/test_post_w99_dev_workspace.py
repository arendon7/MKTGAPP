from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PostW99DevelopmentWorkspaceTests(unittest.TestCase):
    def test_vscode_workspace_json_is_valid_and_targets_serve_dev(self):
        tasks = json.loads((ROOT / ".vscode" / "tasks.json").read_text(encoding="utf-8"))
        launch = json.loads((ROOT / ".vscode" / "launch.json").read_text(encoding="utf-8"))
        extensions = json.loads((ROOT / ".vscode" / "extensions.json").read_text(encoding="utf-8"))
        settings = json.loads((ROOT / ".vscode" / "settings.json").read_text(encoding="utf-8"))

        labels = {task["label"]: task for task in tasks["tasks"]}
        self.assertIn("MKTGAPP: Serve Dev", labels)
        self.assertIn("MKTGAPP: Test All", labels)
        serve_args = labels["MKTGAPP: Serve Dev"]["args"]
        self.assertIn("serve-dev", serve_args)
        self.assertNotIn("serve", serve_args)
        self.assertEqual(labels["MKTGAPP: Serve Dev"]["options"]["env"]["PYTHONPATH"], "${workspaceFolder}/src")

        configuration = launch["configurations"][0]
        self.assertEqual(configuration["module"], "binario_marketing.cli")
        self.assertIn("serve-dev", configuration["args"])
        self.assertEqual(configuration["env"]["PYTHONPATH"], "${workspaceFolder}/src")

        recommendations = set(extensions["recommendations"])
        self.assertIn("ms-python.python", recommendations)
        self.assertIn("ms-python.debugpy", recommendations)
        self.assertIn("Google.google-antigravity", recommendations)

        self.assertEqual(settings["python.analysis.extraPaths"], ["./src"])
        self.assertTrue(settings["python.testing.unittestEnabled"])
        self.assertFalse(settings["python.testing.pytestEnabled"])
        self.assertIn("test_*.py", settings["python.testing.unittestArgs"])

    def test_agent_guardrails_preserve_frozen_release_boundary(self):
        agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        docs = (ROOT / "docs" / "DEVELOPMENT_WORKSPACE.md").read_text(encoding="utf-8")
        for content in (agents, docs):
            self.assertIn(FROZEN_MAIN, content)
            self.assertIn("dev/post-w99-action-center", content)
            self.assertIn("serve-dev", content)
        self.assertIn("do not push or merge source changes to `main`", agents.casefold())
        self.assertIn("no credentials", docs.casefold())

    def test_cli_keeps_distinct_frozen_and_post_w99_entrypoints(self):
        cli = (ROOT / "src" / "binario_marketing" / "cli.py").read_text(encoding="utf-8")
        self.assertIn('sub.add_parser("serve"', cli)
        self.assertIn('sub.add_parser("serve-dev"', cli)
        self.assertIn("from .service_post_w99_dev_app import serve", cli)

    def test_workspace_change_does_not_expand_workflow_surface(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
