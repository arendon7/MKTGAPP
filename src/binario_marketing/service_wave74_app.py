from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from . import service_wave73_app as base

INTERACTION_ASSETS = ("interaction-probe.js", "interaction-audit.js")


class AppRuntime(base.AppRuntime):
    """Wave 74 exposes a read-only interaction-audit contract."""

    def interaction_integrity(self, company_id: str | None = None) -> dict:
        ui = self.ui_integrity(company_id)
        web_root = self.repo_root / "web"
        assets = [{"name": name, "present": (web_root / name).is_file()} for name in INTERACTION_ASSETS]
        missing = [row["name"] for row in assets if not row["present"]]
        return {
            "schema": "binario.marketing.interaction-integrity.v1",
            "ready": bool(ui["ready"] and not missing),
            "company": ui.get("company"),
            "ui_integrity_ready": bool(ui["ready"]),
            "browser_probe_required": True,
            "assets": assets,
            "missing": {"interaction_assets": missing},
            "browser_contract": {
                "views": list(base.UI_VIEWS),
                "visible_controls_scanned": True,
                "unwired_controls_reported": True,
                "programmatic_clicks": False,
                "form_submission": False,
                "provider_activation": False,
            },
            "safety": {"read_only_projection": True, "release_mutation_performed": False},
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
            app_tag = '<script src="/app.js" defer></script>'
            probe_tag = '<script src="/interaction-probe.js" defer data-interaction-probe-wave74="1"></script>'
            if probe_tag not in text:
                if app_tag not in text:
                    self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "base app script marker missing")
                    return
                text = text.replace(app_tag, f"{probe_tag}\n  {app_tag}", 1)
            bootstrap = '<script src="/product-bootstrap.js" defer data-product-bootstrap-wave73="1"></script>'
            entry = '<script src="/product-entry-wave73.js" defer data-product-entry-wave73="1"></script>'
            audit = '<script src="/interaction-audit.js" defer data-interaction-audit-wave74="1"></script>'
            marker = "</body>"
            if marker not in text:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "product entry marker missing")
                return
            if bootstrap not in text:
                text = text.replace(marker, f"  {bootstrap}\n  {entry}\n  {audit}\n{marker}", 1)
            body = text.encode("utf-8")
            self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
            return
        super()._static(path)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"/interaction-probe.js", "/interaction-audit.js"}:
            self._static(path)
            return
        if path == "/api/interaction-integrity":
            try:
                company_id = (parse_qs(parsed.query).get("company_id") or [None])[0]
                self._json(self.server.runtime.interaction_integrity(company_id))
            except Exception as exc:
                self._wave67_error(exc)
            return
        super().do_GET()


def create_server(runtime: AppRuntime, host: str = "127.0.0.1", port: int = 8765) -> MarketingHTTPServer:
    return MarketingHTTPServer((host, port), MarketingHandler, runtime)


def serve(host: str = "127.0.0.1", port: int = 8765, *, allow_network: bool = False, open_browser: bool = False) -> None:
    runtime = AppRuntime.create()
    server = create_server(runtime, host, port)
    try:
        server.serve_forever()
    finally:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown(); runtime.transcriptions.shutdown(); runtime.renders.shutdown(); server.server_close()


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
