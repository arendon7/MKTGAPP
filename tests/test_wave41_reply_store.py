import tempfile
import unittest
from pathlib import Path

from binario_marketing.inbox_reply_store import InboxReplyConflict, InboxReplyStore


class Wave41ReplyStoreTests(unittest.TestCase):
    def test_secret_free_checkpoint_and_ambiguous_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxReplyStore(Path(tmp))
            row, reused = store.begin("company-1", "facebook_message", "msg-1", "Texto privado que no debe persistir")
            self.assertFalse(reused)
            self.assertEqual(row.stage, "SENDING")
            store.ambiguous(row.key)
            raw = (Path(tmp) / f"{row.key}.json").read_text(encoding="utf-8")
            self.assertNotIn("Texto privado", raw)
            self.assertIn(row.text_sha256, raw)
            with self.assertRaises(InboxReplyConflict):
                store.begin("company-1", "facebook_message", "msg-1", "Texto privado que no debe persistir")

    def test_sent_checkpoint_is_reused_without_new_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxReplyStore(Path(tmp))
            row, _ = store.begin("company-1", "instagram_comment", "comment-1", "Gracias")
            sent = store.sent(row.key, "reply-1")
            reused, was_reused = store.begin("company-1", "instagram_comment", "comment-1", "Gracias")
            self.assertTrue(was_reused)
            self.assertEqual(reused.stage, "SENT")
            self.assertEqual(sent.remote_id, "reply-1")


if __name__ == "__main__":
    unittest.main()
