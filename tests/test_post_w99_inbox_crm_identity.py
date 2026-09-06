from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from binario_marketing.inbox_crm_identity import InboxCRMIdentityConflict, InboxCRMIdentityStore
from binario_marketing.service_post_w99_inbox_crm_identity_app import AppRuntime


ROOT = Path(__file__).resolve().parents[1]
COMPANY_A = "company_" + "a" * 24
COMPANY_B = "company_" + "b" * 24
CONTACT_A = "contact_" + "a" * 24
CONTACT_B = "contact_" + "b" * 24


class InboxCRMIdentityStoreTests(unittest.TestCase):
    def test_raw_provider_id_is_never_persisted_and_key_is_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = InboxCRMIdentityStore(root)
            raw_person_id = "17890000123456789"
            row, reused = store.link(COMPANY_A, "facebook", raw_person_id, CONTACT_A)
            self.assertFalse(reused)
            self.assertEqual(row.contact_id, CONTACT_A)
            serialized = "\n".join(path.read_text(encoding="utf-8") for path in (root / "links").glob("*.json"))
            self.assertNotIn(raw_person_id, serialized)
            self.assertNotIn(raw_person_id, str(next((root / "links").glob("*.json"))))
            self.assertEqual(len(row.fingerprint), 64)
            self.assertEqual(len((root / ".identity-key").read_bytes()), 32)
            if os.name == "posix":
                self.assertEqual((root / ".identity-key").stat().st_mode & 0o077, 0)

    def test_fingerprint_scope_and_refresh_bound_intent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxCRMIdentityStore(Path(tmp))
            person = "person-1"
            first = store.fingerprint(COMPANY_A, "facebook", person)
            self.assertEqual(first, store.fingerprint(COMPANY_A, "facebook", person))
            self.assertNotEqual(first, store.fingerprint(COMPANY_B, "facebook", person))
            self.assertNotEqual(first, store.fingerprint(COMPANY_A, "instagram", person))
            token = store.intent_token(COMPANY_A, "facebook", "msg-1", person, "2026-09-06T01:00:00+00:00")
            self.assertTrue(store.verify_intent(COMPANY_A, "facebook", "msg-1", person, "2026-09-06T01:00:00+00:00", token))
            self.assertFalse(store.verify_intent(COMPANY_A, "facebook", "msg-2", person, "2026-09-06T01:00:00+00:00", token))
            self.assertFalse(store.verify_intent(COMPANY_A, "facebook", "msg-1", person, "2026-09-06T01:01:00+00:00", token))

    def test_replacement_requires_expected_current_contact_and_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = InboxCRMIdentityStore(Path(tmp))
            person = "person-2"
            first, _ = store.link(COMPANY_A, "facebook", person, CONTACT_A)
            reused, was_reused = store.link(COMPANY_A, "facebook", person, CONTACT_A)
            self.assertTrue(was_reused)
            self.assertEqual(reused.contact_id, CONTACT_A)
            with self.assertRaises(InboxCRMIdentityConflict):
                store.link(COMPANY_A, "facebook", person, CONTACT_B)
            with self.assertRaises(InboxCRMIdentityConflict):
                store.link(COMPANY_A, "facebook", person, CONTACT_B, expected_contact_id=CONTACT_B, replace_confirmed=True)
            changed, was_reused = store.link(
                COMPANY_A,
                "facebook",
                person,
                CONTACT_B,
                expected_contact_id=first.contact_id,
                replace_confirmed=True,
            )
            self.assertFalse(was_reused)
            self.assertEqual(changed.contact_id, CONTACT_B)

    def test_corrupt_local_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = InboxCRMIdentityStore(root)
            root.joinpath(".identity-key").write_bytes(b"bad")
            with self.assertRaises(ValueError):
                store.fingerprint(COMPANY_A, "facebook", "person-3")


class InboxCRMIdentityRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        company = self.runtime.companies.create("Empresa Inbox")
        self.company = self.runtime.companies.update(company.id, {"facebook_page_id": "page-1"})
        self.contact = self.runtime.crm.create_contact(self.company.id, {"name": "Ana CRM", "organization": "Cliente"})
        self.other = self.runtime.crm.create_contact(self.company.id, {"name": "Otro contacto"})
        self.actor_id = "17890000999999999"
        self.interaction_id = "msg-identity-1"
        self.observed_at = self._capture_current_snapshot()

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def _provider_payload(self, *, crm_contact=None):
        now = datetime.now(timezone.utc).isoformat()
        return {
            "schema": "binario.marketing.social-inbox.v1",
            "configured": True,
            "summary": {"conversations": 1, "comments": 0, "crm_matches": 0},
            "conversations": [{
                "id": "conversation-1",
                "messages": [{
                    "id": self.interaction_id,
                    "created_time": now,
                    "from": {"id": self.actor_id},
                    "to": [{"id": "page-1"}],
                    "message": "Necesito información",
                    "reply_eligible": True,
                    "crm_contact": crm_contact,
                }],
            }],
            "comments": [],
            "warnings": [],
        }

    def _capture_current_snapshot(self):
        payload = self._provider_payload()
        snapshot = self.runtime.inbox_attention_store.capture(
            self.company.id,
            page_id="page-1",
            instagram_id=None,
            payload=payload,
        )
        return snapshot["captured_at"]

    def _link_payload(self, contact_id=None, *, observed_at=None, token=None, expected_contact_id=None, replace_confirmed=False):
        observed = observed_at or self.observed_at
        proof = token or self.runtime.inbox_crm_identities.intent_token(
            self.company.id, "facebook", self.interaction_id, self.actor_id, observed
        )
        return {
            "kind": "facebook_message",
            "interaction_id": self.interaction_id,
            "provider_person_id": self.actor_id,
            "intent_token": proof,
            "observed_at": observed,
            "contact_id": contact_id or self.contact.id,
            "expected_contact_id": expected_contact_id,
            "replace_confirmed": replace_confirmed,
        }

    def test_link_updates_minimized_attention_without_persisting_person_id(self):
        result = self.runtime.link_inbox_crm_identity(self.company.id, self._link_payload())
        self.assertEqual(result["state"], "LINKED")
        self.assertEqual(result["contact"]["id"], self.contact.id)
        self.assertTrue(result["attention_snapshot_updated"])
        self.assertFalse(result["provider_call_performed"])
        self.assertFalse(result["provider_person_id_exposed"])
        self.assertNotIn(self.actor_id, json.dumps(result))

        snapshot = self.runtime.inbox_attention_store.get(self.company.id)
        self.assertEqual(snapshot["items"][0]["crm_contact_id"], self.contact.id)
        self.assertNotIn(self.actor_id, json.dumps(snapshot))
        link_files = list(self.runtime.inbox_crm_identities.links_root.glob("*.json"))
        self.assertEqual(len(link_files), 1)
        self.assertNotIn(self.actor_id, link_files[0].read_text(encoding="utf-8"))

    def test_link_decorates_future_payload_and_explicit_choice_beats_username_match(self):
        self.runtime.link_inbox_crm_identity(self.company.id, self._link_payload())
        username_match = {"id": self.other.id, "name": self.other.name, "organization": None}
        payload = self.runtime._decorate_identity_payload(self.company.id, self._provider_payload(crm_contact=username_match))
        message = payload["conversations"][0]["messages"][0]
        self.assertEqual(message["crm_contact"]["id"], self.contact.id)
        self.assertEqual(message["crm_identity"]["state"], "LINKED_USERNAME_MISMATCH")
        self.assertTrue(message["crm_identity"]["explicit_link_authority"])
        self.assertEqual(message["crm_identity"]["username_contact"]["id"], self.other.id)

    def test_stale_or_forged_refresh_intent_is_rejected(self):
        stale = "2026-09-05T00:00:00+00:00"
        stale_token = self.runtime.inbox_crm_identities.intent_token(
            self.company.id, "facebook", self.interaction_id, self.actor_id, stale
        )
        with self.assertRaises(InboxCRMIdentityConflict):
            self.runtime.link_inbox_crm_identity(
                self.company.id,
                self._link_payload(observed_at=stale, token=stale_token),
            )
        with self.assertRaises(InboxCRMIdentityConflict):
            self.runtime.link_inbox_crm_identity(
                self.company.id,
                self._link_payload(token="0" * 64),
            )
        self.assertIsNone(self.runtime.inbox_crm_identities.get(self.company.id, "facebook", self.actor_id))

    def test_cross_company_contact_is_rejected(self):
        second = self.runtime.companies.create("Otra empresa")
        foreign = self.runtime.crm.create_contact(second.id, {"name": "Contacto ajeno"})
        with self.assertRaises(ValueError):
            self.runtime.link_inbox_crm_identity(self.company.id, self._link_payload(contact_id=foreign.id))


if __name__ == "__main__":
    unittest.main()
