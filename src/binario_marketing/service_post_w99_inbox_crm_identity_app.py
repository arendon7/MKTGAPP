from __future__ import annotations

from copy import deepcopy
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_inbox_reply_reconciliation_app as base
from .inbox_crm_identity import InboxCRMIdentityConflict, InboxCRMIdentityStore


_SCHEMA = "binario.marketing.inbox-crm-identity-link-result.v1"
_KIND_PROVIDER = {
    "facebook_message": "facebook",
    "instagram_comment": "instagram",
}
_LINKED_STATES = {"LINKED", "LINKED_USERNAME_MISMATCH"}


class AppRuntime(base.AppRuntime):
    """Post-W99 terminal: explicitly associate social actors with existing CRM contacts."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.inbox_crm_identities = InboxCRMIdentityStore(
            runtime.data_root / "State" / "social" / "inbox_crm_identity"
        )
        return runtime

    @staticmethod
    def _contact_summary(contact) -> dict:
        return {
            "id": contact.id,
            "name": contact.name,
            "organization": contact.organization,
        }

    def _linked_contact(self, company_id: str, contact_id: str):
        contact = self.crm.get_contact(contact_id)
        if contact.company_id != company_id:
            raise ValueError("linked CRM contact belongs to another company")
        return contact

    def _decorate_identity_item(self, company_id: str, kind: str, item: dict) -> None:
        person = item.get("from")
        person_id = str(person.get("id") or "").strip() if isinstance(person, dict) else ""
        if not person_id:
            return
        provider = _KIND_PROVIDER[kind]
        username_match = item.get("crm_contact") if isinstance(item.get("crm_contact"), dict) else None
        try:
            link = self.inbox_crm_identities.get(company_id, provider, person_id)
        except (ValueError, OSError):
            item["crm_identity"] = {
                "state": "INTEGRITY_BLOCKED",
                "can_link": False,
                "provider_person_id_persisted": False,
                "fingerprint_exposed": False,
            }
            return

        if link is None:
            item["crm_identity"] = {
                "state": "USERNAME_MATCH" if username_match else "UNLINKED",
                "can_link": not bool(username_match),
                "provider_person_id_persisted": False,
                "fingerprint_exposed": False,
            }
            return

        try:
            linked = self._linked_contact(company_id, link.contact_id)
        except (KeyError, ValueError):
            item["crm_contact"] = username_match
            item["crm_identity"] = {
                "state": "BROKEN",
                "can_link": True,
                "current_contact_id": link.contact_id,
                "provider_person_id_persisted": False,
                "fingerprint_exposed": False,
            }
            return

        linked_summary = self._contact_summary(linked)
        item["crm_contact"] = linked_summary
        if username_match and str(username_match.get("id") or "") != linked.id:
            item["crm_identity"] = {
                "state": "LINKED_USERNAME_MISMATCH",
                "can_link": True,
                "current_contact": linked_summary,
                "username_contact": username_match,
                "explicit_link_authority": True,
                "provider_person_id_persisted": False,
                "fingerprint_exposed": False,
            }
            return

        item["crm_identity"] = {
            "state": "LINKED",
            "can_link": True,
            "current_contact": linked_summary,
            "explicit_link_authority": True,
            "provider_person_id_persisted": False,
            "fingerprint_exposed": False,
        }

    def _decorate_identity_payload(self, company_id: str, payload: dict) -> dict:
        result = payload
        matched: set[str] = set()
        linked_items = 0
        for conversation in result.get("conversations") or []:
            if not isinstance(conversation, dict):
                continue
            for message in conversation.get("messages") or []:
                if not isinstance(message, dict):
                    continue
                self._decorate_identity_item(company_id, "facebook_message", message)
                contact = message.get("crm_contact")
                if isinstance(contact, dict) and contact.get("id"):
                    matched.add(str(contact["id"]))
                if (message.get("crm_identity") or {}).get("state") in _LINKED_STATES:
                    linked_items += 1
        for comment in result.get("comments") or []:
            if not isinstance(comment, dict):
                continue
            self._decorate_identity_item(company_id, "instagram_comment", comment)
            contact = comment.get("crm_contact")
            if isinstance(contact, dict) and contact.get("id"):
                matched.add(str(contact["id"]))
            if (comment.get("crm_identity") or {}).get("state") in _LINKED_STATES:
                linked_items += 1
        summary = dict(result.get("summary") or {})
        summary["crm_matches"] = len(matched)
        summary["crm_identity_links"] = linked_items
        result["summary"] = summary
        return result

    def _inbox_attention_payload(self, company_id: str, *, conversation_limit: int = 10) -> dict:
        payload = super()._inbox_attention_payload(company_id, conversation_limit=conversation_limit)
        return self._decorate_identity_payload(company_id, payload)

    def social_inbox(self, company_id: str, *, conversation_limit: int = 10) -> dict:
        payload = self._decorate_identity_payload(
            company_id,
            super().social_inbox(company_id, conversation_limit=conversation_limit),
        )
        return self._annotate_reply_reconciliation(company_id, payload)

    def _attach_link_intents(self, company_id: str, payload: dict, observed_at: str) -> dict:
        def attach(kind: str, item: dict) -> None:
            identity = item.get("crm_identity")
            person = item.get("from")
            person_id = str(person.get("id") or "").strip() if isinstance(person, dict) else ""
            interaction_id = str(item.get("id") or "").strip()
            if not isinstance(identity, dict) or not identity.get("can_link") or not person_id or not interaction_id:
                return
            try:
                token = self.inbox_crm_identities.intent_token(
                    company_id,
                    _KIND_PROVIDER[kind],
                    interaction_id,
                    person_id,
                    observed_at,
                )
            except (ValueError, OSError):
                identity["state"] = "INTEGRITY_BLOCKED"
                identity["can_link"] = False
                return
            identity["intent_token"] = token
            identity["observed_at"] = observed_at

        for conversation in payload.get("conversations") or []:
            if isinstance(conversation, dict):
                for message in conversation.get("messages") or []:
                    if isinstance(message, dict):
                        attach("facebook_message", message)
        for comment in payload.get("comments") or []:
            if isinstance(comment, dict):
                attach("instagram_comment", comment)
        return payload

    def refresh_inbox_attention(self, company_id: str) -> dict:
        result = super().refresh_inbox_attention(company_id)
        observed_at = str((result.get("attention_snapshot") or {}).get("captured_at") or "").strip()
        if observed_at:
            self._attach_link_intents(company_id, result, observed_at)
        return result

    def _patch_attention_contact(self, company_id: str, kind: str, interaction_id: str, contact_id: str) -> bool:
        snapshot = self.inbox_attention_store.get(company_id)
        if snapshot is None:
            return False
        updated = deepcopy(snapshot)
        changed = False
        for item in updated.get("items") or []:
            if not isinstance(item, dict):
                continue
            if item.get("kind") == kind and str(item.get("interaction_id") or "") == interaction_id:
                if item.get("crm_contact_id") != contact_id:
                    item["crm_contact_id"] = contact_id
                    changed = True
        if changed:
            self.inbox_attention_store.save(updated)
        return changed

    def link_inbox_crm_identity(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("Inbox CRM identity payload must be an object")
        allowed = {
            "kind", "interaction_id", "provider_person_id", "intent_token", "observed_at",
            "contact_id", "expected_contact_id", "replace_confirmed",
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported Inbox CRM identity fields: {', '.join(sorted(unknown))}")
        kind = str(payload.get("kind") or "").strip()
        if kind not in _KIND_PROVIDER:
            raise ValueError("unsupported Inbox CRM identity kind")
        interaction_id = self.inbox_crm_identities._interaction_id(payload.get("interaction_id"))
        person_id = self.inbox_crm_identities._person_id(payload.get("provider_person_id"))
        observed_at = self.inbox_crm_identities._observed_at(payload.get("observed_at"))
        contact_id = str(payload.get("contact_id") or "").strip()
        contact = self.crm.get_contact(contact_id)
        if contact.company_id != company.id:
            raise ValueError("CRM contact does not belong to this company")

        attention = super().inbox_attention(company.id)
        snapshot = self.inbox_attention_store.get(company.id)
        if (
            attention.get("snapshot_state") != "CURRENT"
            or snapshot is None
            or str(snapshot.get("captured_at") or "") != observed_at
        ):
            raise InboxCRMIdentityConflict("Inbox evidence changed or is stale. Refresh Meta before linking this identity.")
        if not self.inbox_crm_identities.verify_intent(
            company.id,
            _KIND_PROVIDER[kind],
            interaction_id,
            person_id,
            observed_at,
            payload.get("intent_token"),
        ):
            raise InboxCRMIdentityConflict("Inbox identity intent is invalid or stale. Refresh Meta before linking.")

        before = self.inbox_crm_identities.get(company.id, _KIND_PROVIDER[kind], person_id)
        row, reused = self.inbox_crm_identities.link(
            company.id,
            _KIND_PROVIDER[kind],
            person_id,
            contact.id,
            expected_contact_id=payload.get("expected_contact_id"),
            replace_confirmed=payload.get("replace_confirmed", False),
        )
        replaced = bool(before is not None and before.contact_id != row.contact_id)
        attention_updated = self._patch_attention_contact(company.id, kind, interaction_id, contact.id)
        self.workspace.registries.timeline.append("social.inbox.crm_identity.linked", {
            "company_id": company.id,
            "kind": kind,
            "contact_id": contact.id,
            "reused": reused,
            "replaced": replaced,
            "attention_snapshot_updated": attention_updated,
            "provider_call_performed": False,
            "automatic": False,
            "provider_person_id_logged": False,
            "fingerprint_logged": False,
            "intent_token_logged": False,
        })
        return {
            "schema": _SCHEMA,
            "company_id": company.id,
            "kind": kind,
            "contact": self._contact_summary(contact),
            "state": "LINKED",
            "reused": reused,
            "replaced": replaced,
            "attention_snapshot_updated": attention_updated,
            "provider_call_performed": False,
            "automatic": False,
            "provider_person_id_exposed": False,
            "fingerprint_exposed": False,
            "intent_token_exposed": False,
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds one explicit local identity-link mutation; no provider I/O."""

    def _static(self, path: str) -> None:
        if path == "/inbox-reply-reconciliation.js":
            target = self.server.runtime.repo_root / "web" / "inbox-reply-reconciliation.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99InboxCRMIdentity(){
  if(document.querySelector('script[data-post-w99-inbox-crm-identity]'))return;
  const script=document.createElement('script');
  script.src='/inbox-crm-identity.js';
  script.defer=true;
  script.dataset.postW99InboxCrmIdentity='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/inbox-crm-identity.js":
            target = self.server.runtime.repo_root / "web" / "inbox-crm-identity.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/inbox-crm-identity.js":
            self._static("/inbox-crm-identity.js")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["inbox", "crm-identity-link"]:
                with self.server.mutation_lock:
                    self._json(self.server.runtime.link_inbox_crm_identity(parts[2], self._body()), HTTPStatus.CREATED)
                return
        except Exception as exc:
            if isinstance(exc, InboxCRMIdentityConflict):
                self._error(HTTPStatus.CONFLICT, str(exc))
            elif isinstance(exc, KeyError):
                self._error(HTTPStatus.NOT_FOUND, "CRM contact not found")
            elif isinstance(exc, (ValueError, TypeError)):
                self._error(HTTPStatus.BAD_REQUEST, str(exc))
            else:
                self._wave41_error(exc)
            return
        super().do_POST()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    if host not in {"127.0.0.1", "localhost", "::1"} and not allow_network:
        raise ValueError("refusing non-loopback bind without --allow-network")
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    actual_host, actual_port = server.server_address[:2]
    print(f"BINARIO Marketing App · post-W99 Inbox CRM Identity: http://{actual_host}:{actual_port}/")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://{actual_host}:{actual_port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
