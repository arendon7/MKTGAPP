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

    def test_pro_media_inspector_and_managed_endpoints_are_wired(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        pro = (ROOT / "web/pro-media.js").read_text(encoding="utf-8")
        service = (ROOT / "src/binario_marketing/service.py").read_text(encoding="utf-8")
        for token in (
            "preview-source-select", "proxy-generate", "overlay-form", "overlay-list",
            "subtitle-form", "subtitle-list", "audio-form", "audio-clear", "pro-media.js",
        ):
            self.assertIn(token, html)
        for token in ("overlay_add", "overlay_edit", "subtitle_add", "subtitle_edit", "audio_set", "audio_clear"):
            self.assertIn(token, pro)
        self.assertIn("proxy/file", pro)
        self.assertIn("/subtitles", pro)
        self.assertIn('"/pro-media.js"', service)
        self.assertIn('parts[5] == "proxy"', service)
        self.assertIn('parts[3] == "subtitles"', service)

    def test_ci_syntax_checks_every_browser_javascript_file(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("for script in web/*.js", workflow)
        self.assertIn('node --check "$script"', workflow)


if __name__ == "__main__":
    unittest.main()
