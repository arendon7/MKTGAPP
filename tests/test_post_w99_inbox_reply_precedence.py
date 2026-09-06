from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from binario_marketing.inbox_attention import project_attention


NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


class InboxReplyPrecedenceTests(unittest.TestCase):
    def test_ambiguous_reply_remains_blocking_even_when_crm_followup_exists(self):
        snapshot = {
            "captured_at": NOW.isoformat(),
            "items": [{
                "kind": "facebook_message",
                "interaction_id": "msg_ambiguous",
                "occurred_at": "2026-09-06T11:30:00+00:00",
                "actor_handle": "cliente",
                "crm_contact_id": "contact_" + "b" * 24,
                "excerpt": "Necesito información",
                "reply_eligible": True,
            }],
        }
        activities = [SimpleNamespace(summary="Atender mensaje [MKTGAPP_META_MESSAGE:msg_ambiguous]")]
        result = project_attention(
            snapshot,
            activities=activities,
            stages={("facebook_message", "msg_ambiguous"): "AMBIGUOUS"},
            now=NOW,
        )
        self.assertEqual(len(result["items"]), 1)
        self.assertEqual(result["items"][0]["attention_kind"], "reply_verification")
        self.assertTrue(result["items"][0]["blocking"])
        self.assertEqual(result["items"][0]["rank"], 18)
        self.assertEqual(result["suppressed_by_crm"], 0)

    def test_confirmed_sent_reply_still_suppresses_even_with_crm_marker(self):
        snapshot = {
            "captured_at": NOW.isoformat(),
            "items": [{
                "kind": "facebook_message",
                "interaction_id": "msg_sent",
                "occurred_at": "2026-09-06T11:20:00+00:00",
                "actor_handle": "cliente",
                "crm_contact_id": None,
                "excerpt": "Gracias",
                "reply_eligible": True,
            }],
        }
        activities = [SimpleNamespace(summary="Atender mensaje [MKTGAPP_META_MESSAGE:msg_sent]")]
        result = project_attention(
            snapshot,
            activities=activities,
            stages={("facebook_message", "msg_sent"): "SENT"},
            now=NOW,
        )
        self.assertEqual(result["items"], [])
        self.assertEqual(result["suppressed_by_reply"], 1)
        self.assertEqual(result["suppressed_by_crm"], 0)


if __name__ == "__main__":
    unittest.main()
