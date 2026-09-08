from __future__ import annotations

import json
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.request import urlopen

from binario_marketing.portfolio_inbox import SCHEMA, build_portfolio_inbox
from binario_marketing.service_post_w99_portfolio_inbox_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def company(index: int, name: str, *, mapped: bool = True, active: bool = True):
    return SimpleNamespace(
        id=f"company_{index:024x}",
        name=name,
        active=active,
        facebook_page_id=f"page_{index}" if mapped else None,
        instagram_id=None,
    )


class PortfolioInboxPureTests(unittest.TestCase):
    def test_projection_aggregates_only_configured_active_companies_and_preserves_rank(self):
        first = company(1, "Zeta")
        second = company(2, "Alfa")
        unmapped = company(3, "Sin Meta", mapped=False)
        inactive = company(4, "Inactiva", active=False)
        attention = {
            first.id: {
                "snapshot_state": "CURRENT",
                "captured_at": "2026-09-07T20:00:00+00:00",
                "refresh_required": False,
                "items": [{
                    "kind": "facebook_message", "interaction_id": "msg-1",
                    "occurred_at": "2026-09-07T19:00:00+00:00", "actor_handle": "uno",
                    "excerpt": "Necesito información", "attention_kind": "incoming_message",
                    "rank": 27, "urgency": "HIGH", "blocking": False,
                    "title": "Responder mensaje reciente · @uno",
                }],
            },
            second.id: {
                "snapshot_state": "CURRENT",
                "captured_at": "2026-09-07T20:00:00+00:00",
                "refresh_required": False,
                "items": [{
                    "kind": "instagram_comment", "interaction_id": "comment-1",
                    "occurred_at": "2026-09-07T18:00:00+00:00", "actor_handle": "dos",
                    "excerpt": "¿Precio?", "attention_kind": "reply_verification",
                    "rank": 18, "urgency": "HIGH", "blocking": True,
                    "title": "Verificar respuesta antes de reenviar · @dos",
                }],
            },
        }
        result = build_portfolio_inbox([first, second, unmapped, inactive], attention)
        self.assertEqual(result["schema"], SCHEMA)
        self.assertEqual(result["summary"]["active_companies"], 3)
        self.assertEqual(result["summary"]["configured_companies"], 2)
        self.assertEqual(result["summary"]["attention_total"], 2)
        self.assertEqual(result["queue"][0]["interaction_id"], "comment-1")
        self.assertEqual(result["queue"][0]["company"]["id"], second.id)
        self.assertEqual(result["queue"][0]["action"], {
            "label": "Abrir en Inbox", "view": "inbox",
            "tab": "instagram_comment", "entity_id": "comment-1",
        })
        self.assertFalse(result["safety"]["provider_read_performed"])
        self.assertFalse(result["safety"]["crm_mutation_performed"])

    def test_projection_keeps_minimized_fields_and_no_mapping_ids(self):
        row = company(1, "Marca")
        result = build_portfolio_inbox([row], {row.id: {
            "snapshot_state": "CURRENT", "captured_at": "2026-09-07T20:00:00+00:00",
            "refresh_required": False,
            "items": [{
                "kind": "facebook_message", "interaction_id": "message-safe-id",
                "occurred_at": "2026-09-07T19:00:00+00:00", "actor_handle": "cliente",
                "crm_contact_id": "contact_local", "excerpt": "Texto mínimo",
                "reply_eligible": True, "attention_kind": "incoming_message",
                "rank": 27, "urgency": "HIGH", "blocking": False,
            }],
        }})
        serialized = json.dumps(result)
        self.assertNotIn("page_1", serialized)
        self.assertNotIn("facebook_page_id", serialized)
        self.assertNotIn("instagram_id", serialized)
        self.assertIn("Texto mínimo", serialized)
        self.assertTrue(result["contracts"]["full_provider_bodies_excluded"])

    def test_missing_or_corrupt_local_state_is_refresh_required_not_provider_read(self):
        row = company(1, "Marca")
        result = build_portfolio_inbox([row], {})
        self.assertEqual(result["companies"][0]["snapshot_state"], "LOCAL_STATE_ERROR")
        self.assertTrue(result["companies"][0]["refresh_required"])
        self.assertEqual(result["queue"], [])
        self.assertFalse(result["safety"]["provider_read_performed"])


class PortfolioInboxRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.first = self.runtime.companies.create("Marca Uno")
        self.second = self.runtime.companies.create("Marca Dos")
        self.first = self.runtime.companies.update(self.first.id, {"facebook_page_id": "page_one"})
        self.second = self.runtime.companies.update(self.second.id, {"instagram_id": "ig_two"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_runtime_reads_only_local_attention_snapshots(self):
        now = datetime.now(timezone.utc).isoformat()
        self.runtime.inbox_attention_store.capture(
            self.first.id,
            page_id="page_one",
            instagram_id=None,
            payload={
                "configured": True,
                "conversations": [{"messages": [{
                    "id": "msg-local", "created_time": now,
                    "from": {"id": "person-one", "username": "cliente"},
                    "to": [{"id": "page_one"}], "message": "Hola, quiero comprar",
                    "reply_eligible": True,
                }]}],
                "comments": [],
            },
        )
        provider_calls = []
        self.runtime._inbox_attention_payload = lambda *args, **kwargs: provider_calls.append((args, kwargs))
        result = self.runtime.portfolio_inbox()
        self.assertEqual(provider_calls, [])
        self.assertEqual(result["summary"]["attention_total"], 1)
        self.assertEqual(result["queue"][0]["interaction_id"], "msg-local")
        self.assertEqual(result["queue"][0]["excerpt"], "Hola, quiero comprar")
        self.assertFalse(result["safety"]["provider_read_performed"])

    def test_http_projection_and_static_asset_are_get_only(self):
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/api/portfolio/inbox-attention", timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(payload["schema"], SCHEMA)
            self.assertFalse(payload["safety"]["provider_read_performed"])
            with urlopen(root + "/portfolio-inbox.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_PORTFOLIO_INBOX", source)
            self.assertIn("/api/portfolio/inbox-attention", source)
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_defaults_to_portfolio_and_hands_exact_target_to_owner(self):
        source = (ROOT / "web" / "portfolio-inbox.js").read_text(encoding="utf-8")
        for required in (
            "mode:'PORTFOLIO'", "INBOX / MULTIEMPRESA", "Actualizar todas desde Meta",
            "postW99PortfolioInboxRefreshRun", "portfolioNavigate(companyId,row.action",
            "state.mode='COMPANY'", "Volver a todas las empresas",
            "/api/portfolio/inbox-attention", "Verificar",
        ):
            self.assertIn(required, source)
        self.assertNotIn("method:'POST'", source)
        self.assertNotIn("/api/inbox/meta", source)
        for forbidden in ("setInterval(", "setTimeout(", "MutationObserver", "sendBeacon", "graph.facebook", "fetch('https://", 'fetch("https://'):
            self.assertNotIn(forbidden, source)

    def test_refresh_adapter_exposes_single_existing_explicit_authority(self):
        source = (ROOT / "web" / "portfolio-inbox-refresh.js").read_text(encoding="utf-8")
        self.assertIn("globalThis.postW99PortfolioInboxRefreshRun=run", source)
        self.assertEqual(source.count("method:'POST'"), 1)
        self.assertIn("window.confirm", source)

    def test_source_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_inbox_app", dev)
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_inbox_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_inbox_refresh_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        docs = (ROOT / "docs" / "POST_W99_PORTFOLIO_INBOX.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("sin polling", docs.casefold())


if __name__ == "__main__":
    unittest.main()
