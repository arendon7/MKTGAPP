from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .creative_store import CreativeStore
from . import service_wave48_app as base


class AppRuntime(base.AppRuntime):
    """Wave 49 connects Video Studio, company media, campaigns, calendar and paid-media planning."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.creatives = CreativeStore(runtime.data_root / "State" / "creatives")
        return runtime

    def _creative_payload(self, company_id: str, media) -> dict:
        profile = self.creatives.get(company_id, media.id)
        campaign = None
        publications: list[dict] = []
        paid_media: list[dict] = []
        if profile is not None:
            if profile.campaign_id:
                row = self.campaigns.get_for_company(company_id, profile.campaign_id)
                campaign = {"id": row.id, "name": row.name, "objective": row.objective, "status": row.status}
            for publication_id in profile.publication_ids:
                try:
                    row = self.social.get(publication_id)
                except KeyError:
                    continue
                if row.project_id == company_id:
                    publications.append({
                        "id": row.id,
                        "channel": row.channel,
                        "kind": row.kind,
                        "status": row.status,
                        "scheduled_for": row.scheduled_for,
                        "remote_id": row.remote_id,
                    })
            _company, workspace = self._company_workspace(company_id)
            if workspace is not None:
                for draft_id in profile.paid_media_ids:
                    try:
                        row = self.paid_media.get(draft_id)
                    except KeyError:
                        continue
                    if row.project_id == workspace.project_id:
                        paid_media.append({
                            "id": row.id,
                            "status": row.status,
                            "campaign_name": row.campaign_name,
                            "campaign_id": row.campaign_id,
                            "ad_id": row.ad_id,
                        })
        effective_stage = profile.stage if profile is not None else "UNPROFILED"
        if any(row["status"] == "PUBLISHED" for row in publications):
            effective_stage = "PUBLISHED"
        elif any(row["status"] == "QUEUED" for row in publications):
            effective_stage = "SCHEDULED"
        if paid_media:
            effective_stage = "PAID"
        return {
            "media": {
                **asdict(media),
                "file_url": f"/api/companies/{company_id}/media/{media.id}/file",
            },
            "creative": asdict(profile) if profile is not None else None,
            "campaign": campaign,
            "publications": publications,
            "paid_media": paid_media,
            "effective_stage": effective_stage,
        }

    def company_creatives_payload(self, company_id: str) -> list[dict]:
        company = self.companies.get(company_id)
        return [self._creative_payload(company.id, row) for row in self.company_media.list(company.id)]

    def creative_context(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        rows = self.company_creatives_payload(company.id)
        campaigns = [
            {
                "id": row.id,
                "name": row.name,
                "objective": row.objective,
                "status": row.status,
                "channels": list(row.channels),
                "start_at": row.start_at,
                "end_at": row.end_at,
            }
            for row in self.campaigns.list(company.id)
        ]
        counts = {stage: 0 for stage in ("UNPROFILED", "BRIEF", "DRAFT", "READY", "SCHEDULED", "PUBLISHED", "PAID", "ARCHIVED")}
        for row in rows:
            counts[row["effective_stage"]] = counts.get(row["effective_stage"], 0) + 1
        return {
            "company": asdict(company),
            "campaigns": campaigns,
            "items": rows,
            "counts": counts,
            "meta": {
                "social_ready": bool(company.facebook_page_id or company.instagram_id),
                "ads_ready": bool(company.ad_account_id and company.facebook_page_id),
            },
        }

    def upsert_company_creative(self, company_id: str, media_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        media = self.company_media.get_for_company(company.id, media_id)
        campaign_id = str(payload.get("campaign_id") or "").strip() if isinstance(payload, dict) else ""
        if campaign_id:
            self.campaigns.get_for_company(company.id, campaign_id)
        current = self.creatives.get(company.id, media.id)
        clean = dict(payload)
        if current is None and not str(clean.get("title") or "").strip():
            clean["title"] = media.original_name
        row = self.creatives.upsert(company.id, media.id, clean)
        if row.campaign_id:
            campaign = self.campaigns.get_for_company(company.id, row.campaign_id)
            media_ids = list(campaign.media_ids)
            if media.id not in media_ids:
                media_ids.append(media.id)
                self.campaigns.update(company.id, campaign.id, {"media_ids": media_ids})
        self.workspace.registries.timeline.append("creative.updated", {
            "company_id": company.id,
            "media_id": media.id,
            "stage": row.stage,
            "purpose": row.purpose,
            "campaign_id": row.campaign_id,
            "channels": list(row.channels),
        })
        return self._creative_payload(company.id, media)

    def promote_company_render(self, company_id: str, render_id: str, payload: dict) -> dict:
        company, workspace = self._company_workspace(company_id)
        if workspace is None:
            raise ValueError("company has no Video Studio workspace")
        render = self.renders.get(render_id)
        if render.project_id != workspace.project_id:
            raise KeyError(render_id)
        if render.status != "PASS":
            raise ValueError("only completed PASS renders can be promoted to the company library")
        path = self.renders.output_path(render.id)
        if not path.is_file() or path.stat().st_size <= 0:
            raise FileNotFoundError(path)

        # Promotion is content-addressed: clicking the same completed render twice must
        # not duplicate the company library. Reuse the managed media with matching SHA.
        if render.sha256:
            existing = next(
                (
                    row for row in self.company_media.list(company.id)
                    if row.sha256 == render.sha256 and (render.bytes is None or row.bytes == render.bytes)
                ),
                None,
            )
            if existing is not None:
                if self.creatives.get(company.id, existing.id) is None:
                    clean = dict(payload or {})
                    clean.setdefault("title", str(clean.get("title") or render.output_name))
                    clean.setdefault("stage", "DRAFT")
                    clean.setdefault("purpose", "OTHER")
                    self.creatives.upsert(company.id, existing.id, clean)
                return self._creative_payload(company.id, existing)

        with path.open("rb") as handle:
            media = self.company_media.add_uploaded(company.id, render.output_name, "video", handle, path.stat().st_size)
        try:
            self.probe_company_media(company.id, media.id)
            media = self.company_media.get_for_company(company.id, media.id)
        except Exception:
            pass
        clean = dict(payload or {})
        clean.setdefault("title", str(clean.get("title") or render.output_name))
        clean.setdefault("stage", "DRAFT")
        clean.setdefault("purpose", "OTHER")
        profile = self.creatives.upsert(company.id, media.id, clean)
        if profile.campaign_id:
            campaign = self.campaigns.get_for_company(company.id, profile.campaign_id)
            media_ids = list(campaign.media_ids)
            if media.id not in media_ids:
                media_ids.append(media.id)
                self.campaigns.update(company.id, campaign.id, {"media_ids": media_ids})
        self.workspace.registries.timeline.append("creative.render.promoted", {
            "company_id": company.id,
            "project_id": workspace.project_id,
            "render_id": render.id,
            "media_id": media.id,
            "sha256": media.sha256,
        })
        return self._creative_payload(company.id, media)

    def prepare_creative_publication(self, company_id: str, media_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        media = self.company_media.get_for_company(company.id, media_id)
        creative = self.creatives.get(company.id, media.id)
        if creative is None:
            raise ValueError("save the creative brief before preparing a publication")
        clean = dict(payload or {})
        channel = str(clean.get("channel") or next((c for c in creative.channels if c in {"facebook_page", "instagram"}), "")).strip().lower()
        if channel not in {"facebook_page", "instagram"}:
            raise ValueError("select Facebook or Instagram for the publication")
        message = str(clean.get("message") if "message" in clean else creative.primary_copy).strip()
        scheduled_for = clean.get("scheduled_for") or creative.publish_at
        publication = {
            "channel": channel,
            "message": message,
            "scheduled_for": scheduled_for,
        }
        if media.kind == "video":
            publication.update({"kind": "reel", "asset_id": media.id})
        elif media.kind == "image":
            public_url = str(clean.get("public_media_url") or creative.public_media_url or "").strip()
            if not public_url.startswith("https://"):
                raise ValueError("organic image publishing requires an HTTPS public_media_url reachable by Meta")
            publication.update({"kind": "image", "media_url": public_url})
        else:
            raise ValueError("unsupported creative media kind")
        row = self.create_company_publication(company.id, publication)
        stage = "SCHEDULED" if row["status"] == "QUEUED" else "READY"
        profile = self.creatives.link_publication(company.id, media.id, row["id"], stage=stage)
        if profile.campaign_id:
            campaign = self.campaigns.get_for_company(company.id, profile.campaign_id)
            publication_ids = list(campaign.publication_ids)
            media_ids = list(campaign.media_ids)
            if row["id"] not in publication_ids:
                publication_ids.append(row["id"])
            if media.id not in media_ids:
                media_ids.append(media.id)
            self.campaigns.update(company.id, campaign.id, {
                "publication_ids": publication_ids,
                "media_ids": media_ids,
            })
        self.workspace.registries.timeline.append("creative.publication.prepared", {
            "company_id": company.id,
            "media_id": media.id,
            "publication_id": row["id"],
            "channel": channel,
            "status": row["status"],
            "scheduled_for": row.get("scheduled_for"),
        })
        return {"publication": row, "creative": self._creative_payload(company.id, media)}

    def create_company_paid_media(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("paid media payload must be an object")
        clean = dict(payload)
        creative_media_id = str(clean.pop("creative_media_id", "") or "").strip() or None
        if not creative_media_id and str(clean.get("source_kind") or "").strip().lower() == "company_media":
            candidate = str(clean.get("company_media_id") or "").strip()
            if candidate and self.creatives.get(company_id, candidate) is not None:
                creative_media_id = candidate
        creative = None
        if creative_media_id:
            company = self.companies.get(company_id)
            media = self.company_media.get_for_company(company.id, creative_media_id)
            if media.kind != "image":
                raise ValueError("Paid Media Center currently accepts image creatives from Creative Studio")
            creative = self.creatives.get(company.id, media.id)
            if creative is None:
                raise ValueError("save the creative brief before sending it to Pauta")
            if not str(clean.get("campaign_id") or "").strip() and creative.campaign_id:
                clean["campaign_id"] = creative.campaign_id
            clean["source_kind"] = "company_media"
            clean["company_media_id"] = media.id
            if creative.primary_copy and not str(clean.get("message") or "").strip():
                clean["message"] = creative.primary_copy
            if creative.destination_url and not str(clean.get("link_url") or "").strip():
                clean["link_url"] = creative.destination_url
            if not str(clean.get("call_to_action") or "").strip():
                clean["call_to_action"] = creative.call_to_action
        row = super().create_company_paid_media(company_id, clean)
        if creative_media_id and creative is not None:
            profile = self.creatives.link_paid_media(company_id, creative_media_id, row["id"])
            if profile.campaign_id:
                campaign = self.campaigns.get_for_company(company_id, profile.campaign_id)
                media_ids = list(campaign.media_ids)
                if creative_media_id not in media_ids:
                    media_ids.append(creative_media_id)
                    self.campaigns.update(company_id, campaign.id, {"media_ids": media_ids})
            self.workspace.registries.timeline.append("creative.paid_media.linked", {
                "company_id": company_id,
                "media_id": creative_media_id,
                "draft_id": row["id"],
            })
        return row


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/creative-studio.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "creatives":
                self._json(self.server.runtime.company_creatives_payload(parts[2]))
                return
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["creatives", "context"]:
                self._json(self.server.runtime.creative_context(parts[2]))
                return
        except Exception as exc:
            self._wave47_error(exc)
            return
        super().do_GET()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "creatives":
                with self.server.mutation_lock:
                    result = self.server.runtime.upsert_company_creative(parts[2], parts[4], self._body())
                self._json(result)
                return
        except Exception as exc:
            self._wave47_error(exc)
            return
        super().do_PATCH()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 7 and parts[:2] == ["api", "companies"] and parts[3:5] == ["workspace", "renders"] and parts[6] == "promote":
                with self.server.mutation_lock:
                    result = self.server.runtime.promote_company_render(parts[2], parts[5], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "creatives" and parts[5] == "publication":
                with self.server.mutation_lock:
                    result = self.server.runtime.prepare_creative_publication(parts[2], parts[4], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave47_error(exc)
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
    url = f"http://{actual_host}:{actual_port}/"
    print(f"BINARIO Marketing App: {url}")
    print(f"Data: {runtime.data_root}")
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
