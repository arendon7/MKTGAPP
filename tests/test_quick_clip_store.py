import tempfile
import unittest
from pathlib import Path

from binario_marketing.quick_clip_store import QuickClipStore


SHA="a"*64


def payload(**changes):
    base={
        "asset_id":"asset-1",
        "transcript_sha256":SHA,
        "mode":"objective",
        "target_count":2,
        "min_duration":10,
        "max_duration":40,
        "target_duration":25,
        "aspect":"9:16",
        "clips":[
            {"start":2,"end":25,"text":"Primera idea completa.","score":4.2,"tone":"educativo","reasons":["pregunta/hook"]},
            {"start":30,"end":55,"text":"Segunda idea completa.","score":3.8,"tone":"accionable","reasons":["acción/CTA"]},
        ],
    }
    base.update(changes)
    return base


class QuickClipStoreTests(unittest.TestCase):
    def test_selection_survives_store_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/"quick-clips"
            first=QuickClipStore(root)
            saved=first.save("project_1",payload())
            self.assertEqual(saved.aspect,"9:16")
            self.assertEqual(len(saved.clips),2)
            reopened=QuickClipStore(root).get("project_1")
            self.assertIsNotNone(reopened)
            self.assertEqual(reopened.transcript_sha256,SHA)
            self.assertEqual(reopened.clips[0]["text"],"Primera idea completa.")

    def test_clear_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuickClipStore(Path(tmp))
            store.save("project-2",payload())
            self.assertTrue(store.clear("project-2"))
            self.assertFalse(store.clear("project-2"))
            self.assertIsNone(store.get("project-2"))

    def test_rejects_invalid_hash_mode_bounds_and_empty_clips(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuickClipStore(Path(tmp))
            for bad in (
                payload(transcript_sha256="bad"),
                payload(mode="random"),
                payload(min_duration=40,max_duration=10),
                payload(target_duration=50),
                payload(clips=[]),
            ):
                with self.assertRaises(ValueError):
                    store.save("project-3",bad)

    def test_clip_payload_is_normalized_to_known_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=QuickClipStore(Path(tmp))
            row=payload(clips=[{"start":0,"end":12,"text":"  Texto limpio  ","score":1,"unknown":"drop-me","reasons":[" razón "]}])
            saved=store.save("project-4",row)
            self.assertEqual(saved.clips[0]["text"],"Texto limpio")
            self.assertEqual(saved.clips[0]["reasons"],["razón"])
            self.assertNotIn("unknown",saved.clips[0])


if __name__=="__main__":unittest.main()
