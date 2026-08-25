from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qs, urlparse

from . import service_post_w99_pipeline_priority_app as base


_KIND_ORDER = {"CONTACT": 0, "OPPORTUNITY": 1, "LEAD": 2, "CAMPAIGN": 3, "ACTIVITY": 4, "MEDIA": 5}
_KIND_LABELS = {"CONTACT": "Contacto", "OPPORTUNITY": "Oportunidad", "LEAD": "Lead", "CAMPAIGN": "Campaña", "ACTIVITY": "Seguimiento", "MEDIA": "Contenido"}


def _norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch)).casefold()
    return " ".join(text.split())


def _tokens(value: object) -> tuple[str, ...]:
    return tuple(token for token in re.split(r"[^a-z0-9_@.+-]+", _norm(value)) if token)


def _search_score(query: str, fields: list[tuple[str, object]]) -> tuple[int, str] | None:
    """Deterministic exact/prefix/token search. No fuzzy or semantic inference."""
    q = _norm(query); tokens = _tokens(q)
    if not q or not tokens: return None
    best = 0; matched_field = ""
    for field_name, raw in fields:
        value = _norm(raw)
        if not value: continue
        score = 0
        if value == q: score = 100
        elif value.startswith(q): score = 90
        elif any(word.startswith(q) for word in value.split()): score = 82
        elif q in value: score = 72
        elif all(any(word.startswith(token) for word in value.split()) for token in tokens): score = 66
        elif all(token in value for token in tokens): score = 58
        if score > best: best = score; matched_field = field_name
    if not best:
        combined = " ".join(_norm(raw) for _, raw in fields if raw)
        if combined and all(token in combined for token in tokens): best, matched_field = 50, "multiple_fields"
    return (best, matched_field) if best else None


def _result(*, kind: str, entity_id: str, title: str, subtitle: str, fields: list[tuple[str, object]], action: dict, updated_at: str | None, query: str, status: str | None = None) -> dict | None:
    matched = _search_score(query, fields)
    if matched is None: return None
    score, matched_field = matched
    return {"id": f"{kind.lower()}:{entity_id}", "kind": kind, "kind_label": _KIND_LABELS[kind], "entity_id": entity_id, "title": title, "subtitle": subtitle, "status": status, "match": {"score": score, "field": matched_field, "mode": "DETERMINISTIC_TEXT"}, "updated_at": updated_at, "action": action}


def navigator_search(runtime, company_id: str, query: str, *, limit: int = 25, kind: str | None = None) -> dict:
    company = runtime.companies.get(company_id); query = str(query or "").strip()
    if len(query) < 2: raise ValueError("search query must contain at least 2 characters")
    if len(query) > 120: raise ValueError("search query is too long")
    limit = max(1, min(int(limit), 50)); kind_filter = str(kind or "").strip().upper() or None
    if kind_filter and kind_filter not in _KIND_ORDER: raise ValueError("invalid navigator kind")
    contacts = {row.id: row for row in runtime.crm.list_contacts(company.id)}; results: list[dict] = []
    def add(row: dict | None) -> None:
        if row is not None and (kind_filter is None or row["kind"] == kind_filter): results.append(row)
    for contact in contacts.values():
        subtitle = " · ".join(part for part in (contact.organization, contact.role, contact.email) if part) or "Contacto CRM"
        add(_result(kind="CONTACT", entity_id=contact.id, title=contact.name, subtitle=subtitle, fields=[("name", contact.name), ("organization", contact.organization), ("role", contact.role), ("email", contact.email), ("phone", contact.phone), ("whatsapp", contact.whatsapp), ("instagram", contact.instagram), ("source", contact.source), ("tags", " ".join(contact.tags)), ("notes", contact.notes), ("id", contact.id)], action={"view": "crm", "tab": "contacts", "contact_id": contact.id}, updated_at=contact.updated_at, query=query))
    for opportunity in runtime.crm.list_opportunities(company.id):
        contact = contacts.get(opportunity.contact_id); value = f"{opportunity.currency} {opportunity.value:,}" if opportunity.value is not None else opportunity.currency
        subtitle = " · ".join(part for part in ((contact.name if contact else None), opportunity.stage, value) if part)
        add(_result(kind="OPPORTUNITY", entity_id=opportunity.id, title=opportunity.title, subtitle=subtitle, fields=[("title", opportunity.title), ("stage", opportunity.stage), ("contact", contact.name if contact else None), ("organization", contact.organization if contact else None), ("next_action", opportunity.next_action), ("notes", opportunity.notes), ("currency", opportunity.currency), ("id", opportunity.id)], action={"view": "crm", "tab": "pipeline", "contact_id": opportunity.contact_id, "opportunity_id": opportunity.id}, updated_at=opportunity.updated_at, query=query, status=opportunity.stage))
    intake = runtime.lead_intake_payload(company.id)
    for lead in intake.get("leads") or []:
        name = str(lead.get("name") or lead.get("email") or lead.get("phone") or lead.get("instagram") or "Lead sin identificar")
        subtitle = " · ".join(part for part in (str(lead.get("organization") or ""), str(lead.get("connector") or ""), str(lead.get("status") or "")) if part)
        add(_result(kind="LEAD", entity_id=lead["id"], title=name, subtitle=subtitle, fields=[("name", lead.get("name")), ("organization", lead.get("organization")), ("email", lead.get("email")), ("phone", lead.get("phone")), ("whatsapp", lead.get("whatsapp")), ("instagram", lead.get("instagram")), ("source", lead.get("source")), ("source_ref", lead.get("source_ref")), ("connector", lead.get("connector")), ("status", lead.get("status")), ("id", lead.get("id"))], action={"view": "commercial-desk", "lead_id": lead["id"], "contact_id": lead.get("converted_contact_id"), "opportunity_id": lead.get("converted_opportunity_id")}, updated_at=lead.get("updated_at") or lead.get("received_at"), query=query, status=lead.get("status")))
    for campaign in runtime.campaigns.list(company.id):
        subtitle = f"{campaign.objective} · {campaign.status}" + (f" · {', '.join(campaign.channels)}" if campaign.channels else "")
        add(_result(kind="CAMPAIGN", entity_id=campaign.id, title=campaign.name, subtitle=subtitle, fields=[("name", campaign.name), ("objective", campaign.objective), ("status", campaign.status), ("channels", " ".join(campaign.channels)), ("notes", campaign.notes), ("id", campaign.id)], action={"view": "campaigns", "campaign_id": campaign.id}, updated_at=campaign.updated_at, query=query, status=campaign.status))
    for activity in runtime.crm.list_activities(company.id):
        contact = contacts.get(activity.contact_id); subtitle = " · ".join(part for part in ((contact.name if contact else None), activity.kind, "Completado" if activity.completed_at else "Pendiente") if part)
        add(_result(kind="ACTIVITY", entity_id=activity.id, title=activity.summary, subtitle=subtitle, fields=[("summary", activity.summary), ("kind", activity.kind), ("contact", contact.name if contact else None), ("due_at", activity.due_at), ("id", activity.id)], action={"view": "crm", "tab": "followups", "contact_id": activity.contact_id, "opportunity_id": activity.opportunity_id, "entity_id": activity.id}, updated_at=activity.updated_at, query=query, status="COMPLETED" if activity.completed_at else "PENDING"))
    for media in runtime.company_media.list(company.id):
        dimensions = f"{media.width}×{media.height}" if media.width and media.height else None; subtitle = " · ".join(part for part in (media.kind, dimensions, media.mime_type) if part)
        add(_result(kind="MEDIA", entity_id=media.id, title=media.original_name, subtitle=subtitle, fields=[("filename", media.original_name), ("kind", media.kind), ("mime_type", media.mime_type), ("id", media.id)], action={"view": "content", "media_id": media.id}, updated_at=media.updated_at, query=query))
    results.sort(key=lambda row: (-row["match"]["score"], _KIND_ORDER[row["kind"]], str(row.get("title") or "").casefold(), row["entity_id"])); total = len(results); results = results[:limit]
    by_kind = {key: 0 for key in _KIND_ORDER}
    for row in results: by_kind[row["kind"]] += 1
    return {"schema": "binario.marketing.navigator.v1", "company": {"id": company.id, "name": company.name}, "query": query, "kind_filter": kind_filter, "total_matches": total, "returned": len(results), "by_kind": by_kind, "results": results, "matching_contract": {"accent_insensitive": True, "case_insensitive": True, "exact": True, "prefix": True, "substring": True, "token_match": True, "fuzzy_matching": False, "semantic_embeddings": False, "ai_ranking": False}, "safety": {"company_scoped": True, "local_state_only": True, "provider_read_performed": False, "provider_mutation_performed": False, "business_mutation_performed": False, "ai_generation_performed": False, "automatic_execution": False}}


class AppRuntime(base.AppRuntime):
    """Post-W99 chain with deterministic cross-module Navigator."""
    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime": return super().create(repo_root, data_root)
    def navigator(self, company_id: str, query: str, *, limit: int = 25, kind: str | None = None) -> dict: return navigator_search(self, company_id, query, limit=limit, kind=kind)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path == "/action-center.js":
            target = self.server.runtime.repo_root / "web" / "action-center.js"
            if not target.is_file(): self._error(HTTPStatus.NOT_FOUND, "not found"); return
            bootstrap = """
;(function loadPostW99Navigator(){
  if(document.querySelector('script[data-post-w99-navigator]'))return;
  const navigator=document.createElement('script');
  navigator.src='/navigator.js';
  navigator.defer=true;
  navigator.dataset.postW99Navigator='1';
  document.head.append(navigator);
})();
"""
            body=(target.read_text(encoding="utf-8")+bootstrap).encode("utf-8"); self._headers(HTTPStatus.OK,"application/javascript; charset=utf-8",len(body)); self.wfile.write(body); return
        super()._static(path)
    def do_GET(self) -> None:
        parsed=urlparse(self.path); path=parsed.path
        if path=="/navigator.js": self._static(path); return
        parts=self._segments()
        try:
            if len(parts)==4 and parts[:2]==["api","companies"] and parts[3]=="navigator":
                params=parse_qs(parsed.query,keep_blank_values=True); query=(params.get("q") or [""])[0]; kind=(params.get("kind") or [None])[0]; raw_limit=(params.get("limit") or ["25"])[0]
                try: limit=int(raw_limit)
                except ValueError: raise ValueError("navigator limit must be an integer")
                self._json(self.server.runtime.navigator(parts[2],query,limit=limit,kind=kind)); return
        except KeyError as exc: self._error(HTTPStatus.NOT_FOUND,f"not found: {exc.args[0]}"); return
        except (ValueError,TypeError) as exc: self._error(HTTPStatus.BAD_REQUEST,str(exc)); return
        except Exception as exc: self._error(HTTPStatus.INTERNAL_SERVER_ERROR,f"internal error: {type(exc).__name__}"); return
        super().do_GET()


def create_server(runtime: AppRuntime, host: str="127.0.0.1", port: int=8765) -> MarketingHTTPServer: return MarketingHTTPServer((host,port),MarketingHandler,runtime)


def serve(host: str="127.0.0.1", port: int=8765, *, allow_network: bool=False, open_browser: bool=False) -> None:
    if host not in {"127.0.0.1","localhost","::1"} and not allow_network: raise ValueError("refusing non-loopback bind without --allow-network")
    runtime=AppRuntime.create(); server=create_server(runtime,host,port); actual_host,actual_port=server.server_address[:2]; url=f"http://{actual_host}:{actual_port}/"; print(f"BINARIO Marketing App · post-W99 Navigator: {url}"); print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser; webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        if runtime.social_scheduler is not None: runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__=["AppRuntime","MarketingHandler","MarketingHTTPServer","create_server","navigator_search","serve"]
