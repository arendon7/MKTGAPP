import unittest

from binario_marketing.video.timeline import Timeline


class TimelineTests(unittest.TestCase):
    def test_split_and_lock(self):
        timeline = Timeline()
        clip = timeline.add("asset-1", 0, 20)
        left, right = timeline.split(clip.id, 8)
        self.assertEqual((left.start, left.end), (0, 8))
        self.assertEqual((right.start, right.end), (8, 20))
        timeline.lock(left.id)
        with self.assertRaises(ValueError):
            timeline.delete(left.id)
        self.assertTrue(timeline.delete(right.id))


if __name__ == "__main__":
    unittest.main()
