from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .meta_ads import LinkCreativeSpec, MetaAdsBuilder, PausedAdSetSpec, PausedAdSpec
from .meta_graph import MetaGraphClient, MetaGraphError
from .paid_media_plan_store import PaidMediaPlanStore
from .wave48_meta_ads import Wave48MetaAdsBuilder
from . import service_wave47_app as base


class AppRuntime(base.AppRuntime):
    """Wave 48 joins campaign intent, managed creative, remote readback and paid-media execution."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.paid_media_plans = PaidMediaPlanStore(runtime.data_root / "State" / "paid_media_plans")
        return runtime

    def _paid_media_payload(self, company_id: str, row) -> dict:
        payload = asdict(row)
        plan = self.paid_media_plans.get(row.id)
        if plan is not None:
            if plan.company_id != company_id:
                raise ValueError("paid-media plan metadata does not belong to this company")
            payload["plan"] = asdict(plan)
            if plan.campaign_id:
                campaign = self.campaigns.get_for_company(company_id, plan.campaign_id)
                payload["marketing_campaign"] = {
                    "id": campaign.id,
                    "name": campaign.name,
                    "objective": campaign.objective,
                    "status": campaign.status,
                }
            else:
                payload["marketing_campaign"] = None
            if plan.company_media_id:
                media = self.company_media.get_for_company(company_id, plan.company_media_id)
                payload["creative_source"] = {
                    "id": media.id,
                    "kind": media.kind,
                    "name": media.original_name,
                    "mime_type": media.mime_type,
                    "width": media.width,
                    "height": media.height,
                    "sha256": media.sha256,
                }
            else:
                payload["creative_source"] = None
        else:
            payload["plan"] = None
            payload["marketing_campaign"] = None
            payload["creative_source"] = None
        return payload

    def company_paid_media(self, company_id: str) -> list[dict]:
        _company, workspace = self._company_workspace(company_id)
        if workspace is None:
            return []
        return [self._paid_media_payload(company_id, row) for row in self.paid_media.list(workspace.project_id)]

    def paid_media_context(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
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
        media = [
            {
                "id": row.id,
                "name": row.original_name,
                "kind": row.kind,
                "mime_type": row.mime_type,
                "width": row.width,
                "height": row.height,
                "bytes": row.bytes,
                "sha256": row.sha256,
                "file_url": f"/api/companies/{company.id}/media/{row.id}/file",
            }
            for row in self.company_media.list(company.id)
            if row.kind == "image"
        ]
        account = None
        if company.ad_account_id:
            try:
                account = next(
                    (row for row in MetaGraphClient.from_env().ad_accounts() if row.get("id") == company.ad_account_id),
                    None,
                )
            except Exception:
                account = None
        return {
            "company_id": company.id,
            "campaigns": campaigns,
            "images": media,
            "ad_account": account or {
                "id": company.ad_account_id,
                "name": company.ad_account_name,
                "currency": None,
                "timezone_name": None,
                "account_status": None,
            },
            "safety": {"remote_create_status": "PAUSED", "activation_supported": False},
        }

    def create_company_paid_media(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("paid media payload must be an object")
        company, workspace = self._company_workspace(company_id, ensure=True)
        if not company.ad_account_id:
            raise ValueError("associate a Meta ad account with this company first")
        if not company.facebook_page_id:
            raise ValueError("associate a Facebook Page with this company first")

        plan_payload = {
            key: payload.get(key)
            for key in (
                "campaign_id", "source_kind", "company_media_id", "source_label",
                "currency", "start_at", "end_at", "date_preset", "notes",
            )
        }
        campaign_id = str(plan_payload.get("campaign_id") or "").strip()
        if campaign_id:
            self.campaigns.get_for_company(company.id, campaign_id)

        source_kind = str(plan_payload.get("source_kind") or "public_url").strip().lower()
        clean = dict(payload)
        for key in plan_payload:
            clean.pop(key, None)
        if source_kind == "company_media":
            media_id = str(plan_payload.get("company_media_id") or "").strip()
            media = self.company_media.get_for_company(company.id, media_id)
            if media.kind != "image":
                raise ValueError("paid-media managed creative must be an image")
            self.company_media.verify_file(company.id, media.id)
            plan_payload["source_label"] = media.original_name
            # PaidMediaDraft v1 requires a URL for legacy compatibility. It is never sent
            # to Meta when the Wave 48 plan identifies a managed company image.
            clean["picture_url"] = f"https://managed.binario.invalid/{media.id}"
        else:
            picture_url = str(clean.get("picture_url") or "").strip()
            if not picture_url:
                raise ValueError("public_url creative requires picture_url")
            plan_payload["company_media_id"] = None
            plan_payload["source_label"] = picture_url

        clean["ad_account_id"] = company.ad_account_id
        clean["page_id"] = company.facebook_page_id
        clean["instagram_actor_id"] = company.instagram_id
        row = self.paid_media.create(workspace.project_id, clean)
        try:
            plan = self.paid_media_plans.create(row.id, company.id, plan_payload)
        except Exception:
            self.paid_media.cancel(row.id)
            raise
        self.workspace.registries.timeline.append("company.paid_media.plan.created", {
            "company_id": company.id,
            "project_id": workspace.project_id,
            "draft_id": row.id,
            "campaign_id": plan.campaign_id,
            "source_kind": plan.source_kind,
            "company_media_id": plan.company_media_id,
            "currency": plan.currency,
            "start_at": plan.start_at,
            "end_at": plan.end_at,
        })
        return self._paid_media_payload(company.id, row)

    def create_paid_media_remote_paused(self, project_id: str, draft_id: str) -> dict:
        row = self._paid_media_for_project(project_id, draft_id)
        plan = self.paid_media_plans.get(draft_id)
        if plan is None:
            return super().create_paid_media_remote_paused(project_id, draft_id)
        if row.status == "REMOTE_PAUSED":
            return self._paid_media_payload(plan.company_id, row)
        if row.status != "DRAFT":
            raise ValueError("paid media plan is not eligible for remote creation")

        company = self.companies.get(plan.company_id)
        _company, workspace = self._company_workspace(company.id)
        if workspace is None or workspace.project_id != project_id:
            raise ValueError("paid media plan is not attached to the company's canonical workspace")
        if row.ad_account_id != company.ad_account_id or row.page_id != company.facebook_page_id:
            raise ValueError("paid media plan no longer matches the company's Meta assets")

        client = MetaGraphClient.from_env()
        wave48 = Wave48MetaAdsBuilder(client)
        legacy = MetaAdsBuilder(client)

        if not row.campaign_id:
            remote_id = client.create_paused_campaign(
                row.ad_account_id,
                name=row.campaign_name,
                objective=row.campaign_objective,
                special_ad_categories=row.special_ad_categories,
            )
            row = self.paid_media.checkpoint_remote(row.id, "campaign_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.campaign", {
                "project_id": project_id, "draft_id": row.id, "remote_id": remote_id, "status": "PAUSED",
            })

        if not row.adset_id:
            remote_id = wave48.create_paused_adset(
                PausedAdSetSpec(
                    ad_account_id=row.ad_account_id,
                    campaign_id=row.campaign_id or "",
                    name=row.adset_name,
                    daily_budget=row.daily_budget,
                    optimization_goal=row.optimization_goal,
                    targeting=row.targeting,
                ),
                start_time=plan.start_at,
                end_time=plan.end_at,
            )
            row = self.paid_media.checkpoint_remote(row.id, "adset_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.adset", {
                "project_id": project_id, "draft_id": row.id, "remote_id": remote_id,
                "status": "PAUSED", "start_at": plan.start_at, "end_at": plan.end_at,
            })

        if not row.creative_id:
            spec = LinkCreativeSpec(
                ad_account_id=row.ad_account_id,
                page_id=row.page_id,
                instagram_actor_id=row.instagram_actor_id,
                name=row.creative_name,
                message=row.message,
                link_url=row.link_url,
                picture_url=row.picture_url,
                call_to_action=row.call_to_action,
            )
            if plan.source_kind == "company_media":
                image_hash = plan.image_hash
                if not image_hash:
                    media = self.company_media.get_for_company(company.id, plan.company_media_id or "")
                    path = self.company_media.verify_file(company.id, media.id)
                    image_hash = wave48.upload_managed_image(row.ad_account_id, path)
                    plan = self.paid_media_plans.update_image_hash(company.id, row.id, image_hash)
                    self.workspace.registries.timeline.append("paid_media.remote.image", {
                        "company_id": company.id,
                        "project_id": project_id,
                        "draft_id": row.id,
                        "company_media_id": media.id,
                        "image_hash": image_hash,
                    })
                remote_id = wave48.create_link_creative_from_hash(spec, image_hash)
            else:
                remote_id = legacy.create_link_creative(spec)
            row = self.paid_media.checkpoint_remote(row.id, "creative_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.creative", {
                "project_id": project_id, "draft_id": row.id, "remote_id": remote_id,
            })

        if not row.ad_id:
            remote_id = legacy.create_paused_ad(PausedAdSpec(
                ad_account_id=row.ad_account_id,
                adset_id=row.adset_id or "",
                creative_id=row.creative_id or "",
                name=row.ad_name,
            ))
            row = self.paid_media.checkpoint_remote(row.id, "ad_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.ad", {
                "project_id": project_id, "draft_id": row.id, "remote_id": remote_id, "status": "PAUSED",
            })

        row = self.paid_media.mark_remote_paused(row.id)
        self.workspace.registries.timeline.append("paid_media.remote.complete", {
            "company_id": company.id,
            "project_id": project_id,
            "draft_id": row.id,
            "status": "REMOTE_PAUSED",
            "campaign_id": row.campaign_id,
            "adset_id": row.adset_id,
            "creative_id": row.creative_id,
            "ad_id": row.ad_id,
        })
        return self._paid_media_payload(company.id, row)

    def company_paid_media_observability(self, company_id: str, draft_id: str, date_preset: str | None = None) -> dict:
        company, workspace, row = self._company_paid_media_draft(company_id, draft_id)
        plan = self.paid_media_plans.get_for_company(company.id, row.id)
        preset = str(date_preset or plan.date_preset or "last_7d").strip().lower()
        observed = self.paid_media_observability(workspace.project_id, row.id, date_preset=preset)
        observed["plan"] = asdict(plan)
        if plan.campaign_id:
            campaign = self.campaigns.get_for_company(company.id, plan.campaign_id)
            observed["marketing_campaign"] = {"id": campaign.id, "name": campaign.name, "status": campaign.status}
        else:
            observed["marketing_campaign"] = None
        return observed


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/paid-media-center.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["paid-media", "context"]:
                self._json(self.server.runtime.paid_media_context(parts[2]))
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "paid-media" and parts[5] == "observability":
                query = parse_qs(urlparse(self.path).query)
                preset = (query.get("date_preset") or [None])[0]
                self._json(self.server.runtime.company_paid_media_observability(parts[2], parts[4], preset))
                return
        except Exception as exc:
            self._wave47_error(exc)
            return
        super().do_GET()


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
