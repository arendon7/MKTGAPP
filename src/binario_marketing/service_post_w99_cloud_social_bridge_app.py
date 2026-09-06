from __future__ import annotations

from http import HTTPStatus
from pathlib import Path

from . import service_post_w99_today_portfolio_app as base
from .cloud_social_bridge import CloudSocialBridge, CloudSocialBridgeError, CloudSocialDelegationStore


class AppRuntime(base.AppRuntime):
    """Post-W99 terminal adding explicit desktop-to-cloud social authority handoff."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.cloud_social_delegations = CloudSocialDelegationStore(
            runtime.data_root / "State" / "cloud-social-delegations"
        )
        runtime.cloud_social_bridge = CloudSocialBridge(
            runtime.social,
            runtime.public_gateway_configs,
            runtime.public_gateway_credentials,
            runtime.cloud_social_delegations,
        )
        return runtime

    @staticmethod
    def _publication_summary(rows: list[dict]) -> dict:
        result = base.AppRuntime._publication_summary(rows)
        result["delegated"] = sum(1 for row in rows if str(row.get("status") or "").upper() == "DELEGATED")
        return result

    def cloud_social_overview(self, company_id: str, publication_id: str) -> dict:
        company, row = self._company_publication(company_id, publication_id)
        overview = self.cloud_social_bridge.overview(row.id)
        if overview["company_id"] != company.id:
            raise KeyError(publication_id)
        return overview

    def delegate_company_publication_to_cloud(self, company_id: str, publication_id: str) -> dict:
        company, row = self._company_publication(company_id, publication_id)
        if row.status not in {"QUEUED", "DELEGATED"}:
            raise ValueError("only queued or unconfirmed delegated publications can enter cloud handoff")
        result = self.cloud_social_bridge.delegate(company.id, row.id)
        self.workspace.registries.timeline.append("company.publication.cloud_delegated", {
            "company_id": company.id,
            "publication_id": row.id,
            "local_status": result["local_status"],
            "delegation_status": (result.get("delegation") or {}).get("status"),
            "secret_logged": False,
            "publication_body_logged": False,
        })
        return result

    def retry_company_publication_cloud_enqueue(self, company_id: str, publication_id: str) -> dict:
        company, row = self._company_publication(company_id, publication_id)
        result = self.cloud_social_bridge.retry_enqueue(company.id, row.id)
        self.workspace.registries.timeline.append("company.publication.cloud_enqueue_retried", {
            "company_id": company.id,
            "publication_id": row.id,
            "delegation_status": (result.get("delegation") or {}).get("status"),
            "secret_logged": False,
        })
        return result

    def refresh_company_publication_cloud_status(self, company_id: str, publication_id: str) -> dict:
        company, row = self._company_publication(company_id, publication_id)
        result = self.cloud_social_bridge.refresh_status(company.id, row.id)
        self.workspace.registries.timeline.append("company.publication.cloud_status_refreshed", {
            "company_id": company.id,
            "publication_id": row.id,
            "local_status": result["local_status"],
            "delegation_status": (result.get("delegation") or {}).get("status"),
            "manual_reconciliation": bool(result.get("requires_manual_reconciliation")),
            "secret_logged": False,
        })
        return result


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Explicit local control routes; no cloud polling or automatic delegation."""

    @staticmethod
    def _cloud_route(parts: list[str]) -> tuple[str, str, str] | None:
        if (
            len(parts) == 7
            and parts[:2] == ["api", "companies"]
            and parts[3] == "publications"
            and parts[5] == "cloud"
        ):
            return parts[2], parts[4], parts[6]
        return None

    def _cloud_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, "publication not found")
        elif isinstance(exc, (ValueError, TypeError, CloudSocialBridgeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        route = self._cloud_route(self._segments())
        if route and route[2] == "status":
            try:
                self._json(self.server.runtime.cloud_social_overview(route[0], route[1]))
            except Exception as exc:
                self._cloud_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        route = self._cloud_route(self._segments())
        if route:
            company_id, publication_id, action = route
            try:
                with self.server.mutation_lock:
                    if action == "delegate":
                        self._json(self.server.runtime.delegate_company_publication_to_cloud(company_id, publication_id))
                        return
                    if action == "retry":
                        self._json(self.server.runtime.retry_company_publication_cloud_enqueue(company_id, publication_id))
                        return
                    if action == "refresh":
                        self._json(self.server.runtime.refresh_company_publication_cloud_status(company_id, publication_id))
                        return
                self._error(HTTPStatus.NOT_FOUND, "route not found")
            except Exception as exc:
                self._cloud_error(exc)
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
    print(f"BINARIO Marketing App · post-W99 Cloud Social Bridge: {url}")
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


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
