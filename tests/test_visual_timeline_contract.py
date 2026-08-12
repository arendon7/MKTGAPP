import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class VisualTimelineContractTests(unittest.TestCase):
    def test_visual_timeline_bundle_is_loaded_and_served_locally(self):
        html = (ROOT / "web/index.html").read_text(encoding="utf-8")
        service = (ROOT / "src/binario_marketing/service.py").read_text(encoding="utf-8")
        self.assertIn('<script src="/visual-timeline.js" defer></script>', html)
        self.assertIn('"/visual-timeline.js"', service)

    def test_visual_editor_supports_drag_trim_scrub_and_continuous_preview(self):
        js = (ROOT / "web/visual-timeline.js").read_text(encoding="utf-8")
        for token in (
            "visual-sequence-rail",
            "draggable",
            "dragstart",
            "drop",
            "visual-trim-handle",
            "pointerdown",
            "visual-master-playhead",
            "Previsualizar master",
            "visualLoadMasterTime",
            "visualAdvanceMaster",
            "visualApplyMasterCompositionTime",
            "audio externo se aplica en el render final",
        ):
            self.assertIn(token, js)

    def test_master_scrub_and_transition_are_rate_limited(self):
        js = (ROOT / "web/visual-timeline.js").read_text(encoding="utf-8")
        self.assertIn("addEventListener('change'", js)
        self.assertIn("state.visualTimeline.advancing", js)


if __name__ == "__main__":
    unittest.main()
