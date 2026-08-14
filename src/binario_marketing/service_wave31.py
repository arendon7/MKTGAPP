from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .company_store import Company, CompanyStore
from . import service_wave27 as base
from .wave27_instagram_local import Wave27MetaSocialPublisher


class AppRuntime(base.AppRuntime):
    """Wave 31 company-centric operations layer over the certified social/video runtime."""

    @classmethod
    def create(cls, repo_root: Path | None = None, data_root: Path | None = None) -> "AppRuntime":
        runtime = super().create(repo_root, data_root)
        runtime.companies = CompanyStore(runtime.data_root / "State" / "companies")
        return runtime

    def companies_payload(self, *, include_inactive: bool = False) -> list[dict]:
        return [asdict(row) for row in self.companies.list(include_inactive=include_inactive)]

    def create_company(self, payload: dict) -> dict:
        if not isinstance(payload, dict):
            raise ValueError("company payload must be an object")
        row = self.companies.create(str(payload.get("name") or ""))
        self.workspace.registries.timeline.append("company.created", {
            "company_id": row.id,
            "name": row.name,
        })
        return asdict(row)

    def update_company(self, company_id: str, payload: dict) -> dict:
        row = self.companies.update(company_id, payload)
        self.workspace.registries.timeline.append("company.updated", {
            "company_id": row.id,
            "name": row.name,
            "active": row.active,
        })
        return asdict(row)

    def company_detail(self, company_id: str) -> dict:
        company = self.companies.get(company_id)
        rows = [asdict(row) for row in self.social.list(company.id)]
        return {
            "company": asdict(company),
            "publications": rows,
            "summary": self._publication_summary(rows),
        }

    @staticmethod
    def _publication_summary(rows: list[dict]) -> dict:
        result = {"total": len(rows), "draft": 0, "queued": 0, "published": 0, "failed": 0, "cancelled": 0}
        for row in rows:
            key = str(row.get("status") or "").lower()
            if key in result:
                result[key] += 1
        return result

    def _company_ids(self, company_id: str | None = None) -> tuple[dict[str, Company], set[str]]:
        if company_id:
            row = self.companies.get(company_id)
            return {row.id: row}, {row.id}
        companies = {row.id: row for row in self.companies.list()}
        return companies, set(companies)

    def ops_calendar(self, company_id: str | None = None) -> list[dict]:
        companies, allowed = self._company_ids(company_id)
        rows = []
        for publication in self.social.list():
            if publication.project_id not in allowed:
                continue
            payload = asdict(publication)
            payload["company_id"] = publication.project_id
            payload["company_name"] = companies[publication.project_id].name
            rows.append(payload)
        return sorted(rows, key=lambda row: (row.get("scheduled_for") or row.get("created_at") or "", row.get("id") or ""))

    def ops_dashboard(self, company_id: str | None = None) -> dict:
        companies, _allowed = self._company_ids(company_id)
        rows = self.ops_calendar(company_id)
        now = datetime.now(timezone.utc)
        today = now.date()
        due_today = 0
        overdue = 0
        upcoming = []
        for row in rows:
            when = row.get("scheduled_for")
            if not when or row.get("status") != "QUEUED":
                continue
            parsed = datetime.fromisoformat(str(when).replace("Z", "+00:00")).astimezone(timezone.utc)
            if parsed.date() == today:
                due_today += 1
            if parsed < now:
                overdue += 1
            else:
                upcoming.append(row)
        upcoming.sort(key=lambda row: row.get("scheduled_for") or "")
        summary = self._publication_summary(rows)
        return {
            "company_count": len(companies),
            "summary": summary,
            "scheduled_today": due_today,
            "overdue": overdue,
            "upcoming": upcoming[:8],
            "meta": self.meta_status(),
        }

    def _company_publication(self, company_id: str, publication_id: str):
        company = self.companies.get(company_id)
        row = self.social.get(publication_id)
        if row.project_id != company.id:
            raise KeyError(publication_id)
        return company, row

    @staticmethod
    def _default_target(company: Company, channel: str) -> tuple[str | None, str | None]:
        if channel == "facebook_page":
            return company.facebook_page_id, company.facebook_page_name
        if channel == "instagram":
            label = f"@{company.instagram_username}" if company.instagram_username else None
            return company.instagram_id, label
        return None, None

    def create_company_publication(self, company_id: str, payload: dict) -> dict:
        company = self.companies.get(company_id)
        if not isinstance(payload, dict):
            raise ValueError("publication payload must be an object")
        clean = dict(payload)
        channel = str(clean.get("channel") or "").strip().lower()
        if clean.get("asset_id") or clean.get("render_id"):
            raise ValueError("company composer does not attach project media directly yet; use Content/Video Studio for managed renders")
        if channel == "facebook_page" and str(clean.get("kind") or "").strip().lower() == "reel":
            raise ValueError("Facebook local Reels remain in Content/Video Studio until company media linking is added")
        target_id = str(clean.get("target_id") or "").strip()
        target_name = str(clean.get("target_name") or "").strip()
        if not target_id:
            target_id, default_name = self._default_target(company, channel)
            if target_id:
                clean["target_id"] = target_id
                clean["target_name"] = target_name or default_name or target_id
        if not str(clean.get("target_id") or "").strip():
            raise ValueError("this company has no configured social account for the selected channel")
        row = self.social.create(company.id, clean)
        self.workspace.registries.timeline.append("company.publication.created", {
            "company_id": company.id,
            "publication_id": row.id,
            "channel": row.channel,
            "kind": row.kind,
            "status": row.status,
            "scheduled_for": row.scheduled_for,
        })
        return asdict(row)

    def queue_company_publication(self, company_id: str, publication_id: str, payload: dict) -> dict:
        company, _row = self._company_publication(company_id, publication_id)
        row = self.social.queue(publication_id, payload.get("scheduled_for"))
        self.workspace.registries.timeline.append("company.publication.queued", {
            "company_id": company.id,
            "publication_id": row.id,
            "scheduled_for": row.scheduled_for,
        })
        return asdict(row)

    def cancel_company_publication(self, company_id: str, publication_id: str) -> dict:
        company, row = self._company_publication(company_id, publication_id)
        if row.status not in {"DRAFT", "QUEUED", "FAILED"}:
            raise ValueError("only draft, queued or failed publications can be cancelled")
        row = self.social.transition(publication_id, "CANCELLED")
        self.workspace.registries.timeline.append("company.publication.cancelled", {
            "company_id": company.id,
            "publication_id": row.id,
        })
        return asdict(row)

    def publish_company_publication_now(self, company_id: str, publication_id: str) -> dict:
        company, row = self._company_publication(company_id, publication_id)
        if row.status in {"DRAFT", "FAILED"}:
            row = self.social.queue(publication_id)
        if row.status != "QUEUED":
            raise ValueError("publication cannot be published from its current state")
        scheduler = self.social_scheduler
        if scheduler is None:
            raise RuntimeError("social scheduler is unavailable")
        result = asdict(Wave27MetaSocialPublisher(self.social, scheduler.client_factory()).publish(publication_id))
        self._record_social_results([result])
        self.workspace.registries.timeline.append("company.publication.attempted", {
            "company_id": company.id,
            "publication_id": publication_id,
            "status": result.get("status"),
            "remote_id": result.get("remote_id"),
        })
        return result


MarketingHTTPServer = base.MarketingHTTPServer


class MarketingHandler(base.MarketingHandler):
    """Company-first API/static extension; all certified legacy routes still delegate downward."""

    def _wave31_error(self, exc: Exception) -> None:
        if isinstance(exc, KeyError):
            self._error(HTTPStatus.NOT_FOUND, f"not found: {exc.args[0]}")
        elif isinstance(exc, (ValueError, TypeError)):
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
        else:
            self._error(HTTPStatus.INTERNAL_SERVER_ERROR, f"internal error: {type(exc).__name__}")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/marketing-ops.js", "/marketing-ops.css"}:
            self._static(path)
            return
        parts = self._segments()
        try:
            if parts == ["api", "companies"]:
                query = parse_qs(urlparse(self.path).query)
                include_inactive = (query.get("include_inactive") or ["0"])[0] == "1"
                self._json(self.server.runtime.companies_payload(include_inactive=include_inactive))
                return
            if len(parts) == 3 and parts[:2] == ["api", "companies"]:
                self._json(self.server.runtime.company_detail(parts[2]))
                return
            if parts == ["api", "ops", "dashboard"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.ops_dashboard(company_id))
                return
            if parts == ["api", "ops", "calendar"]:
                query = parse_qs(urlparse(self.path).query)
                company_id = (query.get("company_id") or [None])[0]
                self._json(self.server.runtime.ops_calendar(company_id))
                return
        except Exception as exc:
            self._wave31_error(exc)
            return
        super().do_GET()

    def do_POST(self) -> None:
        parts = self._segments()
        try:
            if parts == ["api", "companies"]:
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_company(self._body()), HTTPStatus.CREATED)
                return
            if len(parts) == 4 and parts[:2] == ["api", "companies"] and parts[3] == "publications":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.create_company_publication(parts[2], self._body()), HTTPStatus.CREATED)
                return
            if len(parts) == 6 and parts[:2] == ["api", "companies"] and parts[3] == "publications":
                with self.server.mutation_lock:
                    if parts[5] == "publish-now":
                        self._json(self.server.runtime.publish_company_publication_now(parts[2], parts[4]))
                        return
                    if parts[5] == "queue":
                        self._json(self.server.runtime.queue_company_publication(parts[2], parts[4], self._body()))
                        return
        except Exception as exc:
            self._wave31_error(exc)
            return
        super().do_POST()

    def do_PATCH(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 3 and parts[:2] == ["api", "companies"]:
                with self.server.mutation_lock:
                    self._json(self.server.runtime.update_company(parts[2], self._body()))
                return
            self._error(HTTPStatus.NOT_FOUND, "route not found")
        except Exception as exc:
            self._wave31_error(exc)

    def do_DELETE(self) -> None:
        parts = self._segments()
        try:
            if len(parts) == 5 and parts[:2] == ["api", "companies"] and parts[3] == "publications":
                with self.server.mutation_lock:
                    self._json(self.server.runtime.cancel_company_publication(parts[2], parts[4]))
                return
        except Exception as exc:
            self._wave31_error(exc)
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


__all__ = ["AppRuntime", "MarketingHandler", "MarketingHTTPServer", "create_server", "serve"]
