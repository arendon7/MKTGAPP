import unittest

from binario_marketing.video.clipper import TranscriptSegment, build_candidates, select_clips


class ClipperTests(unittest.TestCase):
    def setUp(self):
        self.segments = [
            TranscriptSegment(0, 8, "¿Cómo evitar este error en tu campaña?"),
            TranscriptSegment(8, 19, "La clave es definir primero el objetivo."),
            TranscriptSegment(19, 31, "Después mide el resultado antes de escalar."),
            TranscriptSegment(31, 43, "Nunca publiques sin revisar la llamada a la acción."),
            TranscriptSegment(43, 56, "Porque una pieza clara convierte mejor."),
            TranscriptSegment(56, 70, "Cierra con una idea concreta y medible."),
        ]

    def test_candidates_respect_duration(self):
        candidates = build_candidates(self.segments, min_duration=15, max_duration=40)
        self.assertTrue(candidates)
        self.assertTrue(all(15 <= item.duration <= 40 for item in candidates))

    def test_target_count_returns_non_overlapping_social_clips(self):
        clips = select_clips(self.segments, target_count=2, min_duration=15, max_duration=30)
        self.assertEqual(len(clips), 2)
        self.assertLessEqual(clips[0].end, clips[1].start)


if __name__ == "__main__":
    unittest.main()
