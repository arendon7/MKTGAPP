import unittest

from binario_marketing.video.clipper_narrative import NarrativeSegment,generate_candidates,select_narrative_clips


class NarrativeClipperTests(unittest.TestCase):
    def setUp(self):
        self.rows=[
            NarrativeSegment(0,6,'¿Cómo evitar el error que arruina una campaña?'),
            NarrativeSegment(6,13,'Primero define una sola idea central.'),
            NarrativeSegment(13,20,'Después mide si la audiencia realmente la entiende.'),
            NarrativeSegment(20,27,'La clave es ajustar el mensaje, no publicar más por publicar.'),
            NarrativeSegment(27,34,'Pero mucha gente cambia de canal antes de revisar la propuesta.'),
            NarrativeSegment(34,41,'Haz una prueba simple y mide el resultado.'),
            NarrativeSegment(41,48,'Guarda lo que funciona y elimina el ruido.'),
            NarrativeSegment(48,55,'Por eso un buen cierre siempre pide una acción concreta.'),
        ]

    def test_natural_mode_prefers_complete_hook_and_closure(self):
        clips=select_narrative_clips(self.rows,2,mode='natural',min_duration=18,max_duration=30)
        self.assertEqual(len(clips),2)
        self.assertLessEqual(clips[0].end,clips[1].start)
        self.assertTrue(any('pregunta/hook' in row.reasons for row in clips))
        self.assertTrue(all(row.tone in {'educativo','accionable','narrativo','provocativo'} for row in clips))
        self.assertTrue(all(row.text.rstrip().endswith(('.', '!', '?')) for row in clips))

    def test_objective_mode_rewards_target_duration(self):
        candidates=generate_candidates(self.rows,mode='objective',target_duration=21,min_duration=14,max_duration=35)
        self.assertTrue(candidates)
        best=candidates[0]
        self.assertLessEqual(abs(best.duration-21),7)
        self.assertGreater(best.duration_fit,1.0)
        self.assertIn('duración objetivo',best.reasons)

    def test_selection_is_deterministic_and_non_overlapping(self):
        first=select_narrative_clips(self.rows,3,mode='objective',target_duration=14,min_duration=12,max_duration=22)
        second=select_narrative_clips(self.rows,3,mode='objective',target_duration=14,min_duration=12,max_duration=22)
        self.assertEqual(first,second)
        for left,right in zip(first,first[1:]):self.assertLessEqual(left.end,right.start)

    def test_invalid_modes_and_target_bounds_fail_closed(self):
        with self.assertRaises(ValueError):select_narrative_clips(self.rows,1,mode='magic',min_duration=10,max_duration=30)
        with self.assertRaises(ValueError):select_narrative_clips(self.rows,1,mode='objective',target_duration=50,min_duration=10,max_duration=30)


if __name__=='__main__':unittest.main()
