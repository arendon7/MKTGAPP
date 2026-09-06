from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from . import service_post_w99_inbox_action_center_app as base
from .inbox_reply_store import InboxReplyConflict


_RECONCILE_SCHEMA = "binario.marketing.inbox-reply-reconciliation.v1"
_KINDS = {"facebook_message", "instagram_comment"}
_OUTCOMES = {"SENT", "NOT_SENT"}


class AppRuntime(base.AppRuntime):
    """Post-W99 terminal: human reconciliation closes ambiguous Inbox reply attempts."""

    def _decorate_interaction(self, company_id: str, kind: str, item: dict) -> None:
        interaction_id = str(item.get("id") or "").strip()
        if not interaction_id:
            return
        try:
            rows = self.inbox_replies.for_interaction(company_id, kind, interaction_id)
        except (ValueError, OSError):
            item["reply_eligible"] = False
            item["reply_reason"] = "La evidencia local de respuestas requiere revisión de integridad antes de enviar."
            item["reply_reconciliation"] = {
                "required": True,
                "candidates": [],
                "integrity_error": True,
                "provider_read_performed": False,
                "checkpoint_key_exposed": False,
                "text_hash_exposed": False,
            }
            return
        if any(row.stage == "RECONCILED_SENT" for row in rows):
            item["reply_eligible"] = False
            item["reply_reason"] = "Respuesta confirmada manualmente después de verificar Meta."
            item["reply_reconciled_sent"] = True
        candidates = [
            {"stage": row.stage, "updated_at": row.updated_at}
            for row in rows if row.stage in {"SENDING", "AMBIGUOUS"}
        ]
        if candidates:
            item["reply_reconciliation"] = {
                "required": True,
                "candidates": candidates,
                "provider_read_performed": False,
                "checkpoint_key_exposed": False,
                "text_hash_exposed": False,
            }

    def _annotate_reply_reconciliation(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        for conversation in payload.get("conversations") or []:
            if not isinstance(conversation, dict):
                continue
            for message in conversation.get("messages") or []:
                if isinstance(message, dict):
                    self._decorate_interaction(company.id, "facebook_message", message)
        for comment in payload.get("comments") or []:
            if isinstance(comment, dict):
                self._decorate_interaction(company.id, "instagram_comment", comment)
        return payload

    def refresh_inbox_attention(self, company_id: str) -> dict:
        # Parent performs the one explicit Meta read and persists the minimized attention snapshot.
        # Reconciliation metadata is attached afterwards from local checkpoints only and is never persisted in that snapshot.
        return self._annotate_reply_reconciliation(company_id, super().refresh_inbox_attention(company_id))

    def inbox_attention(self, company_id: str) -> dict:
        attention = super().inbox_attention(company_id)
        if not attention.get("items"):
            return attention
        kept: list[dict] = []
        reconciled_sent = 0
        integrity_blocked = 0
        for item in attention.get("items") or []:
            kind = str(item.get("kind") or "")
            interaction_id = str(item.get("interaction_id") or "")
            try:
                rows = self.inbox_replies.for_interaction(company_id, kind, interaction_id) if kind in _KINDS and interaction_id else []
            except (ValueError, OSError):
                blocked = dict(item)
                blocked.update({
                    "attention_kind": "reply_verification",
                    "rank": 18,
                    "urgency": "HIGH",
                    "blocking": True,
                    "title": "Verificar integridad de respuesta social",
                    "detail": "La evidencia local de intentos de respuesta no es íntegra. No se permite reenviar hasta revisar el estado local y Meta.",
                    "reason_code": "INBOX_REPLY_CHECKPOINT_INTEGRITY",
                })
                kept.append(blocked)
                integrity_blocked += 1
                continue
            if any(row.stage == "RECONCILED_SENT" for row in rows):
                reconciled_sent += 1
                continue
            kept.append(item)
        if reconciled_sent or integrity_blocked:
            attention = dict(attention)
            attention["items"] = kept
            attention["suppressed_by_reply"] = int(attention.get("suppressed_by_reply") or 0) + reconciled_sent
            attention["manual_reconciled_sent"] = reconciled_sent
            attention["reply_integrity_blocked"] = integrity_blocked
        return attention

    def reconcile_inbox_reply(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("reply reconciliation payload must be an object")
        allowed = {
            "kind", "interaction_id", "expected_stage", "expected_updated_at", "outcome", "provider_checked"
        }
        unknown = set(payload) - allowed
        if unknown:
            raise ValueError(f"unsupported reply reconciliation fields: {', '.join(sorted(unknown))}")
        kind = str(payload.get("kind") or "").strip()
        interaction_id = str(payload.get("interaction_id") or "").strip()
        expected_stage = str(payload.get("expected_stage") or "").strip().upper()
        expected_updated_at = str(payload.get("expected_updated_at") or "").strip()
        outcome = str(payload.get("outcome") or "").strip().upper()
        if kind not in _KINDS:
            raise ValueError("unsupported inbox reply kind")
        if not interaction_id or len(interaction_id) > 300 or any(ch in interaction_id for ch in "/?#") or any(ch.isspace() for ch in interaction_id):
            raise ValueError("invalid interaction_id")
        if expected_stage not in {"SENDING", "AMBIGUOUS"}:
            raise ValueError("expected_stage must be SENDING or AMBIGUOUS")
        if not expected_updated_at:
            raise ValueError("expected_updated_at is required")
        if outcome not in _OUTCOMES:
            raise ValueError("outcome must be SENT or NOT_SENT")
        if payload.get("provider_checked") is not True:
            raise ValueError("provider_checked must be true after manual Meta verification")

        row = self.inbox_replies.reconcile(
            company.id,
            kind,
            interaction_id,
            expected_stage=expected_stage,
            expected_updated_at=expected_updated_at,
            outcome=outcome,
        )
        self.workspace.registries.timeline.append("social.inbox.reply.reconciled", {
            "company_id": company.id,
            "kind": kind,
            "interaction_id": interaction_id,
            "observed_stage": expected_stage,
            "outcome": outcome,
            "result_stage": row.stage,
            "provider_checked_by_operator": True,
            "provider_call_performed": False,
            "automatic": False,
            "message_body_logged": False,
            "text_hash_logged": False,
            "checkpoint_key_logged": False,
            "remote_id_logged": False,
        })
        return {
            "schema": _RECONCILE_SCHEMA,
            "company_id": company.id,
            "kind": kind,
            "interaction_id": interaction_id,
            "previous_stage": expected_stage,
            "stage": row.stage,
            "outcome": outcome,
            "provider_checked": True,
            "provider_call_performed": False,
            "automatic": False,
            "retry_requires_new_explicit_send": outcome == "NOT_SENT",
            "checkpoint_key_exposed": False,
            "text_hash_exposed": False,
            "remote_id_exposed": False,
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Adds explicit local reconciliation; no route here reads or mutates Meta."""

    def _static(self, path: str) -> None:
        if path == "/inbox-action-center.js":
            target = self.server.runtime.repo_root / "web" / "inbox-action-center.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            bootstrap = """
;(function loadPostW99InboxReplyReconciliation(){
  if(document.querySelector('script[data-post-w99-inbox-reply-reconciliation]'))return;
  const script=document.createElement('script');
  script.src='/inbox-reply-reconciliation.js';
  script.defer=true;
  script.dataset.postW99InboxReplyReconciliation='1';
  document.head.append(script);
})();
"""
            body = (target.read_text(encoding="utf-8") + bootstrap).encode("utf-8")
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        if path == "/inbox-reply-reconciliation.js":
            target = self.server.runtime.repo_root / "web" / "inbox-reply-reconciliation.js"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            body = target.read_bytes()
            self._headers(HTTPStatus.OK, "application/javascript; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        if urlparse(self.path).path == "/inbox-reply-reconciliation.js":
            self._static("/inbox-reply-reconciliation.js")
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["inbox", "reply-reconcile"]:
                with self.server.mutation_lock:
                    self._json(self.server.runtime.reconcile_inbox_reply(parts[2], self._body()))
                return
        except Exception as exc:
            if isinstance(exc, InboxReplyConflict):
                self._error(HTTPStatus.CONFLICT, str(exc))
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
    print(f"BINARIO Marketing App · post-W99 Inbox Reply Reconciliation: http://{actual_host}:{actual_port}/")
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
