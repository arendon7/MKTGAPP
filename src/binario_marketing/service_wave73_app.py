from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from . import service_wave72_app as base


UI_ASSETS = ("product-bootstrap.js", "product-entry-wave73.js", "product-journey.js")
UI_VIEWS = (
    "home", "campaigns", "pauta", "calendar", "publish", "video",
    "content", "crm", "audiences", "analytics", "inbox", "companies",
)


class AppRuntime(base.AppRuntime):
    """Wave 73 closes bootstrap drift and exposes a safe browser-journey integrity contract."""

    def ui_integrity(self, company_id: str | None = None) -> dict:
        web_root = self.repo_root / "web"
        product = self.product_integrity(company_id)
        assets = [{"name": name, "present": (web_root / name).is_file()} for name in UI_ASSETS]
        missing = [row["name"] for row in assets if not row["present"]]
        bootstrap = (web_root / "product-bootstrap.js").read_text(encoding="utf-8") if (web_root / "product-bootstrap.js").is_file() else ""
        journey = (web_root / "product-journey.js").read_text(encoding="utf-8") if (web_root / "product-journey.js").is_file() else ""
        missing_views = [view for view in UI_VIEWS if f"'{view}'" not in journey and f'"{view}"' not in journey]
        deterministic_chain = all(f"/{name}" in bootstrap for name in base.REQUIRED_WEB_ASSETS[7:-1])
        ready = product["ready"] and not missing and not missing_views and deterministic_chain
        return {
            "schema": "binario.marketing.ui-integrity.v1",
            "ready": ready,
            "company": product.get("company"),
            "product_integrity_ready": product["ready"],
            "deterministic_bootstrap": deterministic_chain,
            "assets": assets,
            "views": [{"id": view, "declared": view not in missing_views} for view in UI_VIEWS],
            "inventory": {
                "required_ui_assets": len(assets),
                "present_ui_assets": len(assets) - len(missing),
                "required_views": len(UI_VIEWS),
                "declared_views": len(UI_VIEWS) - len(missing_views),
            },
            "missing": {"ui_assets": missing, "views": missing_views},
            "safety": {
                "read_only_projection": True,
                "browser_check_executes_external_actions": False,
                "browser_check_submits_forms": False,
                "browser_check_clicks_mutating_controls": False,
            },
        }


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    def _static(self, path: str) -> None:
        if path in {"/", "/index.html"}:
            target = self.server.runtime.repo_root / "web" / "index.html"
            if not target.is_file():
                self._error(HTTPStatus.NOT_FOUND, "not found")
                return
            text = target.read_text(encoding="utf-8")
            bootstrap = '<script src="/product-bootstrap.js" defer data-product-bootstrap-wave73="1"></script>'
            entry = '<script src="/product-entry-wave73.js" defer data-product-entry-wave73="1"></script>'
            marker = "</body>"
            if marker not in text:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "product entry marker missing")
                return
            if bootstrap not in text:
                text = text.replace(marker, f"  {bootstrap}\n  {entry}\n{marker}", 1)
            body = text.encode("utf-8")
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/product-bootstrap.js", "/product-entry-wave73.js", "/product-journey.js"}:
            self._static(path)
            return
        if path == "/api/ui-integrity":
            try:
                query = parse_qs(parsed.query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.ui_integrity(company_id))
            except Exception as exc:
                self._wave67_error(exc)
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
