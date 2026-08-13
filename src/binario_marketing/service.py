from __future__ import annotations

import json
import os
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path

from . import service_core as core
from .service_core import *  # re-export the certified Wave 22/23 HTTP/runtime surface
from .meta_ads import LinkCreativeSpec, MetaAdsBuilder, PausedAdSetSpec, PausedAdSpec
from .meta_credentials import MetaCredentialError, MetaCredentialStore
from .meta_graph import MetaGraphClient, MetaGraphError
from .paid_media_store import PaidMediaStore


# Contract-surface markers retained for source-level regression tests. The implementation
# remains byte-for-byte in service_core.py and is inherited below.
# "/transcription.js" "/pro-media.js" "/visual-timeline.js" "/social.js" "/social-uat.js"
# TranscriptionManager transcriptions
# ["transcription", "segments"] ["transcription", "file"] ["transcription", "clips"]
# parts[5] == "proxy"; parts[3] == "subtitles"
# from .sequence_service import start_sequence_render
# parts[3:] == ["renders", "sequence"]
# "quick_clips": selection_for_project(self, project_id)
# save_selection(self.server.runtime, parts[2], payload)
# clear_selection(self.server.runtime, parts[2], reason="user")
# clear_selection_for_asset(self, project_id, asset_id)
# reason="transcription_started"


class AppRuntime(core.AppRuntime):
    """Thin Wave 23 extension over the certified service core."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.paid_media = PaidMediaStore(runtime.data_root / "State" / "paid_media")
        return runtime

    def project_detail(self, project_id: str) -> dict:
        payload = super().project_detail(project_id)
        payload["paid_media"] = [asdict(item) for item in self.paid_media.list(project_id)]
        return payload

    def connect_meta(self, payload: dict) -> dict:
        if os.environ.get("META_ACCESS_TOKEN", "").strip():
            raise MetaCredentialError("Meta connection is controlled by the META_ACCESS_TOKEN environment variable")
        token = str(payload.get("access_token") or "").strip()
        if not token:
            raise ValueError("Meta access token is required")
        version = os.environ.get("META_GRAPH_API_VERSION", "v25.0").strip() or "v25.0"
        identity = MetaGraphClient(token, version).identity()
        credential = MetaCredentialStore().write(token)
        if self.social_scheduler is not None:
            self.social_scheduler.start()
        self.workspace.registries.timeline.append("meta.connected", {
            "identity_id": identity.get("id"),
            "identity_name": identity.get("name"),
            "credential_source": credential.source,
        })
        result = self.meta_status()
        result["identity"] = identity
        return result

    def disconnect_meta(self) -> dict:
        current = MetaCredentialStore().status()
        if current.source == "environment":
            raise MetaCredentialError("Meta connection is controlled by the META_ACCESS_TOKEN environment variable")
        credential = MetaCredentialStore().delete()
        if self.social_scheduler is not None and not credential.configured:
            self.social_scheduler.shutdown()
        self.workspace.registries.timeline.append("meta.disconnected", {"credential_source": current.source})
        return self.meta_status()

    def _paid_media_for_project(self, project_id: str, draft_id: str):
        self._ensure_project(project_id)
        row = self.paid_media.get(draft_id)
        if row.project_id != project_id:
            raise KeyError(draft_id)
        return row

    def create_paid_media_draft(self, project_id: str, payload: dict) -> dict:
        self._ensure_project(project_id)
        row = self.paid_media.create(project_id, payload)
        self.workspace.registries.timeline.append("paid_media.draft.created", {
            "project_id": project_id,
            "draft_id": row.id,
            "ad_account_id": row.ad_account_id,
            "campaign_objective": row.campaign_objective,
            "daily_budget": row.daily_budget,
        })
        return asdict(row)

    def cancel_paid_media_draft(self, project_id: str, draft_id: str) -> dict:
        self._paid_media_for_project(project_id, draft_id)
        row = self.paid_media.cancel(draft_id)
        self.workspace.registries.timeline.append("paid_media.draft.cancelled", {
            "project_id": project_id,
            "draft_id": draft_id,
        })
        return asdict(row)

    def create_paid_media_remote_paused(self, project_id: str, draft_id: str) -> dict:
        row = self._paid_media_for_project(project_id, draft_id)
        if row.status == "REMOTE_PAUSED":
            return asdict(row)
        if row.status != "DRAFT":
            raise ValueError("paid media plan is not eligible for remote creation")

        client = MetaGraphClient.from_env()
        builder = MetaAdsBuilder(client)

        if not row.campaign_id:
            remote_id = client.create_paused_campaign(
                row.ad_account_id,
                name=row.campaign_name,
                objective=row.campaign_objective,
                special_ad_categories=row.special_ad_categories,
            )
            row = self.paid_media.checkpoint_remote(row.id, "campaign_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.campaign", {
                "project_id": project_id,
                "draft_id": row.id,
                "remote_id": remote_id,
                "status": "PAUSED",
            })

        if not row.adset_id:
            remote_id = builder.create_paused_adset(PausedAdSetSpec(
                ad_account_id=row.ad_account_id,
                campaign_id=row.campaign_id or "",
                name=row.adset_name,
                daily_budget=row.daily_budget,
                optimization_goal=row.optimization_goal,
                targeting=row.targeting,
            ))
            row = self.paid_media.checkpoint_remote(row.id, "adset_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.adset", {
                "project_id": project_id,
                "draft_id": row.id,
                "remote_id": remote_id,
                "status": "PAUSED",
            })

        if not row.creative_id:
            remote_id = builder.create_link_creative(LinkCreativeSpec(
                ad_account_id=row.ad_account_id,
                page_id=row.page_id,
                instagram_actor_id=row.instagram_actor_id,
                name=row.creative_name,
                message=row.message,
                link_url=row.link_url,
                picture_url=row.picture_url,
                call_to_action=row.call_to_action,
            ))
            row = self.paid_media.checkpoint_remote(row.id, "creative_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.creative", {
                "project_id": project_id,
                "draft_id": row.id,
                "remote_id": remote_id,
            })

        if not row.ad_id:
            remote_id = builder.create_paused_ad(PausedAdSpec(
                ad_account_id=row.ad_account_id,
                adset_id=row.adset_id or "",
                creative_id=row.creative_id or "",
                name=row.ad_name,
            ))
            row = self.paid_media.checkpoint_remote(row.id, "ad_id", remote_id)
            self.workspace.registries.timeline.append("paid_media.remote.ad", {
                "project_id": project_id,
                "draft_id": row.id,
                "remote_id": remote_id,
                "status": "PAUSED",
            })

        row = self.paid_media.mark_remote_paused(row.id)
        self.workspace.registries.timeline.append("paid_media.remote.complete", {
            "project_id": project_id,
            "draft_id": row.id,
            "status": "REMOTE_PAUSED",
            "campaign_id": row.campaign_id,
            "adset_id": row.adset_id,
            "creative_id": row.creative_id,
            "ad_id": row.ad_id,
        })
        return asdict(row)


MarketingHTTPServer = core.MarketingHTTPServer


class MarketingHandler(core.MarketingHandler):
    """Intercept only Wave 23 extension routes; delegate every legacy route unchanged."""

    def _extension_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, MetaGraphError):
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
        elif isinstance(exc, MetaCredentialError):
            self._error(HTTPStatus.CONFLICT, str(exc))
        elif isinstance(exc, (ValueError, TypeError, json.JSONDecodeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path == "/social-uat.js":
            self._static(path)
            return
        parts = self._segments()
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "paid-media":
            try:
                self.server.runtime._ensure_project(parts[2])
                self._json([asdict(item) for item in self.server.runtime.paid_media.list(parts[2])])
            except Exception as exc:
                self._extension_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        if parts == ["api", "meta", "connection"]:
            try:
                payload = self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.connect_meta(payload)
                self._json(result, HTTPStatus.CREATED)
            except Exception as exc:
                self._extension_error(exc)
            return
        if len(parts) == 4 and parts[:2] == ["api", "projects"] and parts[3] == "paid-media":
            try:
                payload = self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.create_paid_media_draft(parts[2], payload)
                self._json(result, HTTPStatus.CREATED)
            except Exception as exc:
                self._extension_error(exc)
            return
        if len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "paid-media" and parts[5] == "create-paused":
            try:
                self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.create_paid_media_remote_paused(parts[2], parts[4])
                self._json(result, HTTPStatus.CREATED)
            except Exception as exc:
                self._extension_error(exc)
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        parts = self._segments()
        if parts == ["api", "meta", "connection"]:
            try:
                with self.server.mutation_lock:
                    result = self.server.runtime.disconnect_meta()
                self._json(result)
            except Exception as exc:
                self._extension_error(exc)
            return
        if len(parts) == 5 and parts[:2] == ["api", "projects"] and parts[3] == "paid-media":
            try:
                with self.server.mutation_lock:
                    result = self.server.runtime.cancel_paid_media_draft(parts[2], parts[4])
                self._json(result)
            except Exception as exc:
                self._extension_error(exc)
            return
        super().do_DELETE()


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
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()
        server.server_close()