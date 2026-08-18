from __future__ import annotations

import hashlib
from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .creative_bridge_store import CreativeBridgeStore
from . import service_wave48_app as base


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


class AppRuntime(base.AppRuntime):
    """Wave 49 makes the company library the reusable output surface of Creative Studio."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.creative_bridge = CreativeBridgeStore(runtime.data_root / "State" / "creative_bridge")
        return runtime

    def _creative_workspace(self, company_id: str):
        company = self.companies.get(company_id)
        workspace = self.company_workspaces.get(company.id)
        if workspace is None:
            return company, None
        self.projects.path_for(workspace.project_id)
        return company, workspace

    def _bridge_map(self, company_id: str) -> dict[tuple[str, str], dict]:
        return {
            (row.source_type, row.source_id): asdict(row)
            for row in self.creative_bridge.list(company_id)
        }

    def creative_studio_summary(self, company_id: str) -> dict:
        company, workspace = self._creative_workspace(company_id)
        bridges = self._bridge_map(company.id)
        assets = []
        renders = []
        if workspace is not None:
            for row in self.projects.assets(workspace.project_id):
                assets.append({
                    **asdict(row),
                    "promoted": bridges.get(("project_asset", row.id)),
                    "promotable": row.kind in {"image", "video"},
                })
            for row in self.renders.list(workspace.project_id):
                renders.append({
                    **asdict(row),
                    "promoted": bridges.get(("render", row.id)),
                    "promotable": row.status == "PASS" and bool(row.sha256) and bool(row.bytes),
                })
        library = [
            {
                **asdict(row),
                "file_url": f"/api/companies/{company.id}/media/{row.id}/file",
            }
            for row in self.company_media.list(company.id)
        ]
        campaigns = [
            {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "objective": row.objective,
                "media_ids": list(row.media_ids),
            }
            for row in self.campaigns.list(company.id)
        ]
        return {
            "company_id": company.id,
            "workspace": None if workspace is None else {
                "project_id": workspace.project_id,
                "project_name": self.projects.path_for(workspace.project_id).name,
            },
            "assets": assets,
            "renders": renders,
            "library": library,
            "campaigns": campaigns,
            "bridge_count": len(bridges),
        }

    def _creative_source(self, company_id: str, source_type: str, source_id: str) -> dict:
        company, workspace = self._creative_workspace(company_id)
        if workspace is None:
            raise ValueError("open Creative Studio for this company before promoting media")
        source = str(source_type or "").strip()
        source_id = str(source_id or "").strip()
        if source == "project_asset":
            row = self.projects.asset(workspace.project_id, source_id)
            if row.kind not in {"image", "video"}:
                raise ValueError("only image or video project assets can be promoted")
            path = self.projects.asset_path(workspace.project_id, row.id)
            digest, size = _sha256_file(path)
            if row.sha256 and digest.lower() != row.sha256.lower():
                raise ValueError("project asset SHA-256 no longer matches its managed record")
            if row.bytes is not None and size != row.bytes:
                raise ValueError("project asset size no longer matches its managed record")
            return {
                "company": company,
                "workspace": workspace,
                "source_type": source,
                "source_id": row.id,
                "sha256": digest,
                "bytes": size,
                "path": path,
                "filename": row.name,
                "kind": row.kind,
                "width": None,
                "height": None,
                "duration": None,
            }
        if source == "render":
            row = self.renders.get(source_id)
            if row.project_id != workspace.project_id:
                raise KeyError(source_id)
            if row.status != "PASS":
                raise ValueError("only PASS renders can be promoted")
            if not row.sha256 or not row.bytes:
                raise ValueError("render is missing certified SHA/size evidence")
            path = self.renders.output_path(row.id)
            digest, size = _sha256_file(path)
            if digest.lower() != row.sha256.lower():
                raise ValueError("render SHA-256 no longer matches its certified record")
            if size != row.bytes:
                raise ValueError("render size no longer matches its certified record")
            return {
                "company": company,
                "workspace": workspace,
                "source_type": source,
                "source_id": row.id,
                "sha256": digest,
                "bytes": size,
                "path": path,
                "filename": row.output_name,
                "kind": "video",
                "width": row.width,
                "height": row.height,
                "duration": row.duration,
            }
        raise ValueError("source_type must be project_asset or render")

    def promote_company_creative(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("creative promotion payload must be an object")
        unknown = set(payload) - {"source_type", "source_id"}
        if unknown:
            raise ValueError(f"unsupported creative promotion fields: {', '.join(sorted(unknown))}")
        source = self._creative_source(company_id, payload.get("source_type"), payload.get("source_id"))
        company = source["company"]
        workspace = source["workspace"]
        existing = self.creative_bridge.find_source(
            company.id, workspace.project_id, source["source_type"], source["source_id"], source["sha256"]
        )
        if existing is not None:
            media = self.company_media.get_for_company(company.id, existing.company_media_id)
            self.company_media.verify_file(company.id, media.id)
            if media.sha256.lower() != source["sha256"].lower():
                raise ValueError("creative bridge points to company media with a different SHA-256")
            return {"bridge": asdict(existing), "media": asdict(media), "reused": True}

        media = None
        for candidate in self.company_media.list(company.id):
            if candidate.kind == source["kind"] and candidate.sha256.lower() == source["sha256"].lower():
                self.company_media.verify_file(company.id, candidate.id)
                media = candidate
                break
        reused = media is not None
        if media is None:
            with source["path"].open("rb") as handle:
                media = self.company_media.add_uploaded(
                    company.id, source["filename"], source["kind"], handle, source["bytes"]
                )
            if media.sha256.lower() != source["sha256"].lower():
                raise ValueError("promoted company media SHA-256 differs from source")
            media = self.company_media.update_probe(
                company.id,
                media.id,
                width=source["width"],
                height=source["height"],
                duration=source["duration"],
            )
        bridge = self.creative_bridge.create(
            company_id=company.id,
            project_id=workspace.project_id,
            source_type=source["source_type"],
            source_id=source["source_id"],
            source_sha256=source["sha256"],
            company_media_id=media.id,
        )
        self.workspace.registries.timeline.append("creative.promoted", {
            "company_id": company.id,
            "project_id": workspace.project_id,
            "source_type": source["source_type"],
            "source_id": source["source_id"],
            "source_sha256": source["sha256"],
            "company_media_id": media.id,
            "deduplicated": reused,
        })
        return {"bridge": asdict(bridge), "media": asdict(media), "reused": reused}

    def attach_company_media_to_campaign(self, company_id: str, media_id: str, campaign_id: str) -> dict:
        company = self.companies.get(company_id)
        media = self.company_media.get_for_company(company.id, media_id)
        self.company_media.verify_file(company.id, media.id)
        campaign = self.campaigns.get_for_company(company.id, campaign_id)
        media_ids = list(campaign.media_ids)
        changed = media.id not in media_ids
        if changed:
            media_ids.append(media.id)
            campaign = self.campaigns.update(company.id, campaign.id, {"media_ids": media_ids})
            self.workspace.registries.timeline.append("campaign.media.attached", {
                "company_id": company.id,
                "campaign_id": campaign.id,
                "company_media_id": media.id,
            })
        return {"campaign": asdict(campaign), "media": asdict(media), "changed": changed}


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/creative-studio-center.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "creative-studio":
                self._json(self.server.runtime.creative_studio_summary(parts[2]))
                return
        except Exception as exc:
            self._wave47_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3:] == ["creative-studio", "promote"]:
                with self.server.mutation_lock:
                    result = self.server.runtime.promote_company_creative(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if (
                len(parts) == 8
                and parts[:2] == ["api", "companies"]
                and parts[3] == "creative-studio"
                and parts[4] == "media"
                and parts[6] == "campaigns"
            ):
                self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.attach_company_media_to_campaign(parts[2], parts[5], parts[7])
                self._json(result)
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
