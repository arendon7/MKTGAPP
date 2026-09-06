from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from binario_marketing.inbox_reply_store import InboxReplyConflict, InboxReplyStore
from binario_marketing.service_post_w99_inbox_reply_reconciliation_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]


class InboxReplyReconciliationStoreTests(unittest.TestCase):
    def test_changed_text_cannot_bypass_ambiguous_interaction(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxReplyStore(Path(tmp))
            row, _ = store.begin("company-1", "facebook_message", "msg-1", "Texto A")
            ambiguous = store.ambiguous(row.key)
            self.assertEqual(ambiguous.stage, "AMBIGUOUS")
            with self.assertRaises(InboxReplyConflict):
                store.begin("company-1", "facebook_message", "msg-1", "Texto B")
            self.assertEqual(
                store.reconciliation_candidates("company-1", "facebook_message", "msg-1"),
                [{"stage": "AMBIGUOUS", "updated_at": ambiguous.updated_at}],
            )

    def test_not_sent_resolution_only_restores_future_explicit_send_authority(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxReplyStore(Path(tmp))
            row, _ = store.begin("company-1", "instagram_comment", "comment-1", "Gracias")
            ambiguous = store.ambiguous(row.key)
            resolved = store.reconcile(
                "company-1", "instagram_comment", "comment-1",
                expected_stage="AMBIGUOUS", expected_updated_at=ambiguous.updated_at, outcome="NOT_SENT",
            )
            self.assertEqual(resolved.stage, "RETRY_ALLOWED")
            self.assertIsNone(resolved.remote_id)
            self.assertEqual(store.reconciliation_candidates("company-1", "instagram_comment", "comment-1"), [])
            # Reconciliation itself did not send. A separate explicit begin is still required.
            retry, reused = store.begin("company-1", "instagram_comment", "comment-1", "Gracias")
            self.assertFalse(reused)
            self.assertEqual(retry.stage, "SENDING")

    def test_sent_resolution_is_terminal_without_inventing_remote_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxReplyStore(Path(tmp))
            row, _ = store.begin("company-1", "facebook_message", "msg-1", "Hola")
            ambiguous = store.ambiguous(row.key)
            resolved = store.reconcile(
                "company-1", "facebook_message", "msg-1",
                expected_stage="AMBIGUOUS", expected_updated_at=ambiguous.updated_at, outcome="SENT",
            )
            self.assertEqual(resolved.stage, "RECONCILED_SENT")
            self.assertIsNone(resolved.remote_id)
            with self.assertRaises(InboxReplyConflict):
                store.begin("company-1", "facebook_message", "msg-1", "Otro texto")

    def test_stale_or_non_unique_reconciliation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxReplyStore(Path(tmp))
            row, _ = store.begin("company-1", "facebook_message", "msg-1", "Hola")
            ambiguous = store.ambiguous(row.key)
            with self.assertRaises(InboxReplyConflict):
                store.reconcile(
                    "company-1", "facebook_message", "msg-1",
                    expected_stage="AMBIGUOUS", expected_updated_at="stale", outcome="NOT_SENT",
                )

            # Simulate historical pre-hardening drift: a second blocker with another text.
            key2, sha2 = store.identity("company-1", "facebook_message", "msg-1", "Otro")
            payload = {
                "key": key2, "company_id": "company-1", "kind": "facebook_message", "interaction_id": "msg-1",
                "text_sha256": sha2, "stage": "AMBIGUOUS", "remote_id": None,
                "created_at": ambiguous.created_at, "updated_at": ambiguous.updated_at + "x",
            }
            (Path(tmp) / f"{key2}.json").write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(len(store.reconciliation_candidates("company-1", "facebook_message", "msg-1")), 2)
            with self.assertRaises(InboxReplyConflict):
                store.reconcile(
                    "company-1", "facebook_message", "msg-1",
                    expected_stage="AMBIGUOUS", expected_updated_at=ambiguous.updated_at, outcome="SENT",
                )


class InboxReplyReconciliationRuntimeTests(unittest.TestCase):
    def test_runtime_requires_manual_provider_checked_and_returns_secret_free_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp))
            company = runtime.companies.create("Empresa prueba")
            row, _ = runtime.inbox_replies.begin(company.id, "facebook_message", "msg-1", "Contenido privado")
            ambiguous = runtime.inbox_replies.ambiguous(row.key)
            with self.assertRaises(ValueError):
                runtime.reconcile_inbox_reply(company.id, {
                    "kind": "facebook_message", "interaction_id": "msg-1", "expected_stage": "AMBIGUOUS",
                    "expected_updated_at": ambiguous.updated_at, "outcome": "SENT", "provider_checked": False,
                })
            result = runtime.reconcile_inbox_reply(company.id, {
                "kind": "facebook_message", "interaction_id": "msg-1", "expected_stage": "AMBIGUOUS",
                "expected_updated_at": ambiguous.updated_at, "outcome": "SENT", "provider_checked": True,
            })
            self.assertEqual(result["stage"], "RECONCILED_SENT")
            self.assertFalse(result["provider_call_performed"])
            self.assertFalse(result["checkpoint_key_exposed"])
            self.assertFalse(result["text_hash_exposed"])
            self.assertFalse(result["remote_id_exposed"])
            self.assertNotIn("Contenido privado", json.dumps(result))

    def test_refresh_decoration_exposes_only_stage_time_and_closes_reconciled_sent(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp))
            company = runtime.companies.create("Empresa prueba")
            row, _ = runtime.inbox_replies.begin(company.id, "facebook_message", "msg-1", "Privado")
            ambiguous = runtime.inbox_replies.ambiguous(row.key)
            payload = {"conversations": [{"messages": [{"id": "msg-1", "reply_eligible": True}]}], "comments": []}
            decorated = runtime._annotate_reply_reconciliation(company.id, payload)
            candidate = decorated["conversations"][0]["messages"][0]["reply_reconciliation"]["candidates"][0]
            self.assertEqual(candidate, {"stage": "AMBIGUOUS", "updated_at": ambiguous.updated_at})
            encoded = json.dumps(decorated)
            self.assertNotIn(row.key, encoded)
            self.assertNotIn(row.text_sha256, encoded)

            runtime.inbox_replies.reconcile(
                company.id, "facebook_message", "msg-1",
                expected_stage="AMBIGUOUS", expected_updated_at=ambiguous.updated_at, outcome="SENT",
            )
            payload2 = {"conversations": [{"messages": [{"id": "msg-1", "reply_eligible": True}]}], "comments": []}
            item = runtime._annotate_reply_reconciliation(company.id, payload2)["conversations"][0]["messages"][0]
            self.assertFalse(item["reply_eligible"])
            self.assertTrue(item["reply_reconciled_sent"])
            self.assertNotIn("reply_reconciliation", item)


class InboxReplyReconciliationContractTests(unittest.TestCase):
    def test_terminal_route_is_local_reconciliation_not_provider_execution(self):
        source = (ROOT / "src" / "binario_marketing" / "service_post_w99_inbox_reply_reconciliation_app.py").read_text(encoding="utf-8")
        self.assertIn("reply-reconcile", source)
        self.assertIn("provider_checked", source)
        self.assertIn("provider_call_performed", source)
        self.assertNotIn("MetaGraphClient", source)
        self.assertNotIn("MetaInboxWriter", source)
        self.assertNotIn("._request(", source)
        self.assertNotIn("setInterval", source)

    def test_browser_requires_two_human_decisions_and_never_polls_or_calls_meta(self):
        source = (ROOT / "web" / "inbox-reply-reconciliation.js").read_text(encoding="utf-8")
        self.assertIn("window.confirm", source)
        self.assertIn("Sí, se envió", source)
        self.assertIn("No se envió", source)
        self.assertIn("provider_checked:true", source)
        self.assertIn("reply-reconcile", source)
        self.assertNotIn("setInterval", source)
        self.assertNotIn("MutationObserver", source)
        self.assertNotIn("https://graph", source)
        self.assertNotIn("publish-now", source)

    def test_dev_bundle_and_workflows_preserve_frozen_boundaries(self):
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        builder = (ROOT / "scripts" / "build_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        audit = (ROOT / "scripts" / "audit_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        smoke = (ROOT / "scripts" / "smoke_post_w99_dev_mac_app.sh").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_inbox_reply_reconciliation_app", dev)
        for source in (builder, audit):
            self.assertIn("service_post_w99_inbox_reply_reconciliation_app.py", source)
            self.assertIn("inbox-reply-reconciliation.js", source)
        self.assertIn("inbox-reply-reconciliation.js", smoke)
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", builder)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])


if __name__ == "__main__":
    unittest.main()
