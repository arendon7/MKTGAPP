import unittest

from binario_marketing.video.session import EditorSession, Overlay, Subtitle


class EditorSessionTests(unittest.TestCase):
    def test_editing_history_and_reset(self):
        editor = EditorSession()
        clip = editor.add_clip("a1", 0, 20)
        editor.trim(clip.id, 1, 18)
        editor.move(clip.id, 2)
        editor.set_aspect_ratio("9:16")
        editor.add_subtitle(Subtitle("s1", 1, 4, "Hola"))
        editor.edit_subtitle("s1", "Hola mundo")
        editor.add_overlay(Overlay("o1", "logo", 0, 5, behind_subject=True))
        self.assertEqual(editor.aspect_ratio, "9:16")
        self.assertEqual(editor.subtitles[0].text, "Hola mundo")
        self.assertTrue(editor.overlays[0].behind_subject)
        self.assertTrue(editor.undo())
        self.assertEqual(editor.overlays, [])
        self.assertTrue(editor.redo())
        self.assertEqual(len(editor.overlays), 1)
        editor.reset()
        self.assertEqual(editor.timeline.clips, [])
        self.assertEqual(editor.aspect_ratio, "16:9")


if __name__ == "__main__":
    unittest.main()
