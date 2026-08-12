import unittest
from pathlib import Path

from binario_marketing.clipper_service import select_clips_payload
from binario_marketing.video.clipper import TranscriptSegment


ROOT=Path(__file__).resolve().parents[1]


class ClipperModesContractTests(unittest.TestCase):
    def setUp(self):
        self.rows=[
            TranscriptSegment(0,7,'¿Cómo mejorar tu contenido?'),
            TranscriptSegment(7,14,'Primero define una sola idea.'),
            TranscriptSegment(14,21,'Después mide el resultado.'),
            TranscriptSegment(21,28,'La clave es ajustar el mensaje.'),
            TranscriptSegment(28,35,'Haz una prueba y guarda lo que funciona.'),
            TranscriptSegment(35,42,'Cierra con una acción concreta.'),
        ]

    def test_legacy_payload_still_uses_legacy_shape(self):
        clips=select_clips_payload(self.rows,{'target_count':1,'min_duration':14,'max_duration':28})
        self.assertEqual(len(clips),1)
        self.assertIn('score',clips[0]);self.assertNotIn('tone',clips[0])

    def test_narrative_payload_returns_explainable_metadata(self):
        clips=select_clips_payload(self.rows,{'target_count':1,'min_duration':14,'max_duration':28,'mode':'natural'})
        self.assertEqual(len(clips),1);row=clips[0]
        for key in ('tone','hook_score','closure_score','duration_fit','reasons'):self.assertIn(key,row)

    def test_objective_payload_uses_requested_target(self):
        clips=select_clips_payload(self.rows,{'target_count':1,'min_duration':14,'max_duration':35,'mode':'objective','target_duration':21})
        self.assertEqual(len(clips),1);self.assertLessEqual(abs((clips[0]['end']-clips[0]['start'])-21),7)

    def test_browser_bundle_exposes_both_modes(self):
        js=(ROOT/'web/clipper-modes.js').read_text(encoding='utf-8')
        for token in ('Natural · idea completa','Duración objetivo','clipperModePayload','clipper-target-duration','hook + idea autocontenida'):
            self.assertIn(token,js)

    def test_bundle_is_loaded_after_transcription(self):
        html=(ROOT/'web/index.html').read_text(encoding='utf-8')
        self.assertIn('<script src="/clipper-modes.js" defer></script>',html)
        self.assertLess(html.index('/transcription.js'),html.index('/clipper-modes.js'))


if __name__=='__main__':unittest.main()
