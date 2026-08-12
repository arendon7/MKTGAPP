import unittest

from binario_marketing.video.reframe import FocusPoint, safe_zones, smart_reframe_plan


class ReframeTests(unittest.TestCase):
    def test_vertical_crop_tracks_focus_inside_frame(self):
        plan = smart_reframe_plan(1920, 1080, (9, 16), FocusPoint(0.8, 0.5))
        self.assertGreater(plan["height"], 0)
        self.assertGreater(plan["width"], 0)
        self.assertGreaterEqual(plan["x"], 0)
        self.assertGreaterEqual(plan["y"], 0)

    def test_lower_third_and_subtitle_safe_zones_do_not_overlap(self):
        zones = safe_zones(1080, 1920)
        self.assertLess(zones["lower_third"]["bottom"], zones["subtitle"]["top"])


if __name__ == "__main__":
    unittest.main()
