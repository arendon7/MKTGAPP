from __future__ import annotations

from pathlib import Path

from . import service_wave55_app as base


class AppRuntime(base.AppRuntime):
    """Certified Wave 55 runtime with fail-closed attribution preflight before CRM writes."""

    def convert_lead(self, company_id: str, lead_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        lead = self.lead_intake.get(company.id, lead_id)
        # Re-resolve the immutable Wave 53 tracking link before any CRM mutation.
        # Intake already validated this evidence, but durable state is a local file and
        # must not be trusted blindly at conversion time.
        self._lead_attribution_prepared(company.id, lead)
        return super().convert_lead(company.id, lead.id, payload)


MarketingHTTPServer = base.MarketingHTTPServer
MarketingHandler = base.MarketingHandler


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
