import unittest

from binario_marketing.video.audio import AudioSource, AudioSyncSample, alignment_plan, choose_best_audio, normalization_plan


class AudioTests(unittest.TestCase):
    def test_best_external_audio_can_replace_weaker_source(self):
        camera = AudioSource("camera", "Camera", 0.6, 0.4, 0.1)
        external = AudioSource("external", "External", 0.95, 0.1, 0.0)
        best = choose_best_audio([camera, external])
        self.assertEqual(best.id, "external")
        plan = normalization_plan(best)
        self.assertTrue(plan["preserve_sync"])
        self.assertTrue(plan["replace_original_when_rendering"])

    def test_alignment_detects_offset_and_drift(self):
        plan = alignment_plan([
            AudioSyncSample(0.10, 0.00),
            AudioSyncSample(60.20, 60.00),
        ])
        self.assertAlmostEqual(plan["offset_seconds"], 0.1, places=6)
        self.assertTrue(plan["correction_required"])


if __name__ == "__main__":
    unittest.main()
