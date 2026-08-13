import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class CiEfficiencyTests(unittest.TestCase):
    def test_full_mac_build_runs_on_main_and_pull_requests_not_feature_pushes(self):
        workflow = (ROOT / ".github/workflows/full-mac-app.yml").read_text(encoding="utf-8")
        self.assertIn("branches: [main]", workflow)
        self.assertIn("pull_request:", workflow)
        self.assertNotIn('branches: [main, "feature/**", "wave/**"]', workflow)

    def test_source_and_full_mac_cancel_superseded_runs_for_same_branch(self):
        for name in ("ci.yml", "full-mac-app.yml"):
            workflow = (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            self.assertIn("concurrency:", workflow)
            self.assertIn("github.head_ref || github.ref_name", workflow)
            self.assertIn("cancel-in-progress: true", workflow)


if __name__ == "__main__":
    unittest.main()
