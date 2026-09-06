from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from binario_marketing.inbox_attention import (
    InboxAttentionStore,
    build_snapshot,
    extend_action_center,
    project_attention,
    reply_stages,
)


ROOT = Path(__file__).resolve().parents[1]
COMPANY = "company_" + "a" * 24
NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)


def _payload() -> dict:
    return {
        "configured": True,
        "conversations": [
            {
                "id": "conversation-secret-link-not-stored",
                "link": "https://facebook.example/private/thread",
                "messages": [
                    {
                        "id": "msg_new",
                        "created_time": "2026-09-06T11:30:00+00:00",
                        "from": {"id": "person-provider-id", "username": "cliente.uno"},
                        "to": [{"id": "page-1", "username": "brand"}],
                        "message": "Necesito información " + "x" * 700,
                        "crm_contact": {"id": "contact_" + "b" * 24, "name": "Cliente Uno"},
                        "reply_eligible": True,
                        "unavailable": False,
                    },
                    {
                        "id": "msg_old",
                        "created_time": "2026-09-06T10:00:00+00:00",
                        "from": {"id": "person-provider-id", "username": "cliente.uno"},
                        "to": [{"id": "page-1"}],
                        "message": "mensaje anterior",
                        "reply_eligible": True,
                        "unavailable": False,
                    },
                ],
            },
            {
                "id": "conversation_answered",
                "messages": [
                    {
                        "id": "msg_outgoing",
                        "created_time": "2026-09-06T11:50:00+00:00",
                        "from": {"id": "page-1", "username": "brand"},
                        "to": [{"id": "person-2"}],
                        "message": "Ya te respondimos",
                        "reply_eligible": False,
                        "unavailable": False,
                    },
                    {
                        "id": "msg_prior_incoming",
                        "created_time": "2026-09-06T11:40:00+00:00",
                        "from": {"id": "person-2", "username": "cliente.dos"},
                        "to": [{"id": "page-1"}],
                        "message": "Pregunta",
                        "reply_eligible": True,
                        "unavailable": False,
                    },
                ],
            },
        ],
        "comments": [
            {
                "id": "comment_1",
                "media_id": "media-private-not-stored",
                "from": {"id": "ig-person-id", "username": "cliente.tres"},
                "text": "¿Tienen disponibilidad?",
                "timestamp": "2026-09-06T11:20:00+00:00",
                "crm_contact": None,
                "reply_eligible": True,
            },
            {
                "id": "comment_self",
                "media_id": "media-private-not-stored",
                "from": {"id": "ig-brand", "username": "brand"},
                "text": "respuesta propia",
                "timestamp": "2026-09-06T11:10:00+00:00",
                "reply_eligible": False,
            },
        ],
        "warnings": ["provider error with private details"],
        "access_token": "must-never-persist",
    }


class InboxAttentionSnapshotTests(unittest.TestCase):
    def test_snapshot_keeps_only_latest_incoming_and_minimized_comment(self):
        snapshot = build_snapshot(
            COMPANY,
            page_id="page-1",
            instagram_id="ig-brand",
            payload=_payload(),
            captured_at=NOW,
        )
        self.assertEqual([row["interaction_id"] for row in snapshot["items"]], ["msg_new", "comment_1"])
        encoded = json.dumps(snapshot, ensure_ascii=False)
        for forbidden in (
            "person-provider-id",
            "ig-person-id",
            "facebook.example",
            "conversation-secret-link-not-stored",
            "media-private-not-stored",
            "must-never-persist",
            "provider error with private details",
            "msg_old",
            "msg_outgoing",
        ):
            self.assertNotIn(forbidden, encoded)
        message = next(row for row in snapshot["items"] if row["interaction_id"] == "msg_new")
        self.assertEqual(message["actor_handle"], "cliente.uno")
        self.assertLessEqual(len(message["excerpt"]), 280)
        self.assertEqual(message["crm_contact_id"], "contact_" + "b" * 24)

    def test_store_is_company_scoped_and_atomic_shape_round_trips(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxAttentionStore(Path(tmp))
            snapshot = build_snapshot(COMPANY, page_id="page-1", instagram_id="ig-brand", payload=_payload(), captured_at=NOW)
            store.save(snapshot)
            self.assertEqual(store.get(COMPANY), snapshot)
            self.assertEqual(len(list(Path(tmp).glob("company_*.json"))), 1)


class InboxAttentionProjectionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = build_snapshot(
            COMPANY, page_id="page-1", instagram_id="ig-brand", payload=_payload(), captured_at=NOW
        )

    def test_current_snapshot_suppresses_sent_reply_and_crm_followup(self):
        activities = [SimpleNamespace(summary="Atender comentario [MKTGAPP_META_COMMENT:comment_1]")]
        attention = project_attention(
            self.snapshot,
            activities=activities,
            stages={("facebook_message", "msg_new"): "SENT"},
            now=NOW + timedelta(minutes=10),
        )
        self.assertEqual(attention["items"], [])
        self.assertEqual(attention["suppressed_by_reply"], 1)
        self.assertEqual(attention["suppressed_by_crm"], 1)
        self.assertFalse(attention["provider_read_performed"])

    def test_recent_incoming_message_is_high_and_comment_is_medium(self):
        attention = project_attention(self.snapshot, activities=[], stages={}, now=NOW + timedelta(minutes=10))
        self.assertEqual([row["interaction_id"] for row in attention["items"]], ["msg_new", "comment_1"])
        self.assertEqual(attention["items"][0]["urgency"], "HIGH")
        self.assertEqual(attention["items"][0]["rank"], 27)
        self.assertEqual(attention["items"][1]["urgency"], "MEDIUM")

    def test_ambiguous_reply_is_elevated_without_allowing_blind_retry(self):
        attention = project_attention(
            self.snapshot,
            activities=[],
            stages={("facebook_message", "msg_new"): "AMBIGUOUS"},
            now=NOW + timedelta(minutes=10),
        )
        row = attention["items"][0]
        self.assertEqual(row["attention_kind"], "reply_verification")
        self.assertTrue(row["blocking"])
        self.assertEqual(row["rank"], 18)
        self.assertIn("verifica Meta", row["detail"])

    def test_stale_or_missing_snapshot_requests_refresh_but_does_not_claim_old_work(self):
        stale = project_attention(self.snapshot, activities=[], stages={}, now=NOW + timedelta(hours=13))
        missing = project_attention(None, activities=[], stages={}, now=NOW)
        self.assertEqual(stale["snapshot_state"], "STALE")
        self.assertEqual(stale["items"], [])
        self.assertTrue(stale["refresh_required"])
        self.assertEqual(missing["snapshot_state"], "MISSING")
        self.assertTrue(missing["refresh_required"])

    def test_reply_stage_reader_never_treats_corruption_as_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "bad.json").write_text("not json", encoding="utf-8")
            (root / "good.json").write_text(json.dumps({
                "company_id": COMPANY,
                "kind": "facebook_message",
                "interaction_id": "msg_new",
                "stage": "SENT",
            }), encoding="utf-8")
            self.assertEqual(reply_stages(root, COMPANY), {("facebook_message", "msg_new"): "SENT"})


class InboxActionCenterIntegrationTests(unittest.TestCase):
    def test_inbox_extends_existing_priority_authority_without_replacing_order(self):
        base = {
            "queue": [{
                "id": "operations:publication_failed:x", "rank": 0, "urgency": "CRITICAL",
                "source": "OPERATIONS", "kind": "publication_failed", "blocking": True,
                "due_at": None, "action": {"view": "calendar"},
            }],
            "summary": {"active_campaigns": 3},
            "contracts": {},
            "safety": {"provider_read_performed": False},
        }
        attention = {
            "snapshot_state": "CURRENT", "captured_at": NOW.isoformat(), "refresh_required": False,
            "suppressed_by_crm": 0, "suppressed_by_reply": 0,
            "items": [{
                "kind": "facebook_message", "interaction_id": "msg_new", "occurred_at": NOW.isoformat(),
                "actor_handle": "cliente", "crm_contact_id": None, "attention_kind": "incoming_message",
                "rank": 27, "urgency": "HIGH", "blocking": False, "title": "Responder mensaje reciente · @cliente",
                "detail": "Hola", "reason_code": "INBOX_EXPLICIT_REFRESH_ATTENTION",
            }],
        }
        result = extend_action_center(base, attention)
        self.assertEqual(result["queue"][0]["source"], "OPERATIONS")
        self.assertEqual(result["queue"][1]["source"], "INBOX")
        self.assertEqual(result["queue"][1]["action"]["view"], "inbox")
        self.assertEqual(result["summary"]["by_source"]["INBOX"], 1)
        self.assertEqual(result["summary"]["active_campaigns"], 3)
        self.assertFalse(result["safety"]["inbox_provider_read_performed"])

    def test_missing_snapshot_adds_only_low_refresh_handoff(self):
        result = extend_action_center(
            {"queue": [], "summary": {}, "contracts": {}, "safety": {}},
            {"snapshot_state": "MISSING", "captured_at": None, "refresh_required": True,
             "suppressed_by_crm": 0, "suppressed_by_reply": 0, "items": []},
        )
        self.assertEqual(len(result["queue"]), 1)
        self.assertEqual(result["queue"][0]["kind"], "inbox_refresh")
        self.assertEqual(result["queue"][0]["urgency"], "LOW")


class InboxActionCenterSourceContractTests(unittest.TestCase):
    def test_refresh_is_explicit_post_and_attention_read_is_local_get(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_inbox_action_center_app.py").read_text(encoding="utf-8")
        self.assertIn('"refresh-attention"', service)
        self.assertIn('"attention"', service)
        self.assertIn("def _inbox_attention_payload", service)
        self.assertIn("payload = self._inbox_attention_payload(company.id, conversation_limit=10)", service)
        self.assertEqual(service.count("super().social_inbox("), 1)
        self.assertIn("def do_POST", service)
        self.assertIn("def do_GET", service)
        self.assertNotIn("setInterval", service)

    def test_browser_adapter_replaces_only_human_refresh_and_never_polls(self):
        browser = (ROOT / "web" / "inbox-action-center.js").read_text(encoding="utf-8")
        self.assertIn("refresh-attention", browser)
        self.assertIn("method:'POST'", browser)
        self.assertIn("inboxRefresh=async function", browser)
        self.assertNotIn("setInterval", browser)
        self.assertNotIn("MutationObserver", browser)
        self.assertNotIn("inboxRefresh();", browser)

    def test_dev_terminal_and_mac_bundle_move_to_inbox_action_center(self):
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_inbox_action_center_app", dev)
        for source in (builder, audit):
            self.assertIn("service_post_w99_inbox_action_center_app.py", source)
            self.assertIn("inbox-action-center.js", source)
        self.assertIn("inbox-action-center.js", smoke)
        self.assertIn("refresh-attention", smoke)

    def test_no_fourth_workflow_and_frozen_w99_boundary(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        docs = (ROOT / "docs" / "POST_W99_INBOX_ACTION_CENTER.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("no consulta meta", docs.casefold())


if __name__ == "__main__":
    unittest.main()
