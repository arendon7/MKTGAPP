import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class EditorWorkspaceUiContractTests(unittest.TestCase):
    def test_preview_timeline_and_finder_controls_are_present(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        js = (ROOT / "web/app.js").read_text(encoding="utf-8")
        for token in ("preview-stage", "timeline-visual", "open-project-folder", "preview-mark-start", "preview-mark-end"):
            self.assertIn(token, html)
        self.assertIn("/assets/${id}/file", js)
        self.assertIn("previewAsset", js)
        self.assertIn("markSelected", js)
        self.assertIn("event.code==='Space'", js)
        self.assertIn("event.metaKey||event.ctrlKey", js)

    def test_ci_syntax_checks_browser_javascript(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("node --check web/app.js", workflow)


if __name__ == "__main__":
    unittest.main()
