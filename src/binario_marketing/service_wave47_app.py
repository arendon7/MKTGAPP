from __future__ import annotations

from dataclasses import asdict
from http import HTTPStatus
from pathlib import Path
from urllib.parse import urlparse

from .company_workspace import CompanyWorkspaceStore
from .meta_graph import MetaGraphError
from . import service_wave45_app as base


class AppRuntime(base.AppRuntime):
    """Wave 47 makes company context the product-level bridge to Studio and Paid Media."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.company_workspaces = CompanyWorkspaceStore(
            runtime.data_root / "State" / "company_workspaces",
            runtime.projects,
        )
        return runtime

    def _company_workspace(self, company_id: str, *, ensure: bool = False):
        company = self.companies.get(company_id)
        row = self.company_workspaces.get(company.id)
        if row is None and ensure:
            row = self.company_workspaces.ensure(company)
            self.workspace.registries.timeline.append("company.workspace.created", {
                "company_id": company.id,
                "project_id": row.project_id,
            })
        return company, row

    def company_workspace_summary(self, company_id: str) -> dict:
        company, row = self._company_workspace(company_id)
        if row is None:
            return {
                "company_id": company.id,
                "project_id": None,
                "project_name": None,
                "assets": 0,
                "renders": 0,
                "paid_media": 0,
            }
        detail = self.project_detail(row.project_id)
        return {
            "company_id": company.id,
            "project_id": row.project_id,
            "project_name": detail["project"]["name"],
            "assets": len(detail.get("assets") or []),
            "renders": len(detail.get("renders") or []),
            "paid_media": len(detail.get("paid_media") or []),
        }

    def ensure_company_workspace(self, company_id: str) -> dict:
        self._company_workspace(company_id, ensure=True)
        return self.company_workspace_summary(company_id)

    def company_paid_media(self, company_id: str) -> list[dict]:
        _company, row = self._company_workspace(company_id)
        if row is None:
            return []
        return [asdict(item) for item in self.paid_media.list(row.project_id)]

    def create_company_paid_media(self, company_id: str, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("paid media payload must be an object")
        company, workspace = self._company_workspace(company_id, ensure=True)
        if not company.ad_account_id:
            raise ValueError("associate a Meta ad account with this company first")
        if not company.facebook_page_id:
            raise ValueError("associate a Facebook Page with this company first")
        safe = dict(payload)
        # Company-owned Meta identity is authoritative; the browser cannot redirect a
        # paid-media draft to an arbitrary ad account/Page.
        safe["ad_account_id"] = company.ad_account_id
        safe["page_id"] = company.facebook_page_id
        safe["instagram_actor_id"] = company.instagram_id
        row = self.create_paid_media_draft(workspace.project_id, safe)
        self.workspace.registries.timeline.append("company.paid_media.draft.created", {
            "company_id": company.id,
            "project_id": workspace.project_id,
            "draft_id": row["id"],
        })
        return row

    def _company_paid_media_draft(self, company_id: str, draft_id: str):
        company, workspace = self._company_workspace(company_id)
        if workspace is None:
            raise KeyError(draft_id)
        row = self.paid_media.get(draft_id)
        if row.project_id != workspace.project_id:
            raise KeyError(draft_id)
        if company.ad_account_id and row.ad_account_id != company.ad_account_id:
            raise ValueError("paid media draft no longer matches the company's associated ad account")
        return company, workspace, row

    def create_company_paid_media_remote_paused(self, company_id: str, draft_id: str) -> dict:
        company, workspace, _row = self._company_paid_media_draft(company_id, draft_id)
        result = self.create_paid_media_remote_paused(workspace.project_id, draft_id)
        self.workspace.registries.timeline.append("company.paid_media.remote_paused", {
            "company_id": company.id,
            "project_id": workspace.project_id,
            "draft_id": draft_id,
            "status": result.get("status"),
        })
        return result

    def cancel_company_paid_media(self, company_id: str, draft_id: str) -> dict:
        _company, workspace, _row = self._company_paid_media_draft(company_id, draft_id)
        return self.cancel_paid_media_draft(workspace.project_id, draft_id)


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _wave47_error(self, exc: Exception) -> None:
        if isinstance(exc, MetaGraphError):
            self._error(HTTPStatus.BAD_GATEWAY, str(exc))
            return
        self._wave32_error(exc)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/product-shell.js":
            self._static(path)
            return
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "workspace":
                self._json(self.server.runtime.company_workspace_summary(parts[2]))
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "paid-media":
                self._json(self.server.runtime.company_paid_media(parts[2]))
                return
        except Exception as exc:
            self._wave47_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "workspace":
                self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.ensure_company_workspace(parts[2])
                self._json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "paid-media":
                with self.server.mutation_lock:
                    result = self.server.runtime.create_company_paid_media(parts[2], self._body())
                self._json(result, HTTPStatus.CREATED)
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "paid-media" and parts[5] == "create-paused":
                self._body()
                with self.server.mutation_lock:
                    result = self.server.runtime.create_company_paid_media_remote_paused(parts[2], parts[4])
                self._json(result, HTTPStatus.CREATED)
                return
        except Exception as exc:
            self._wave47_error(exc)
            return
        super().do_POST()

    def do_DELETE(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "paid-media":
                with self.server.mutation_lock:
                    result = self.server.runtime.cancel_company_paid_media(parts[2], parts[4])
                self._json(result)
                return
        except Exception as exc:
            self._wave47_error(exc)
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
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown()
        server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
