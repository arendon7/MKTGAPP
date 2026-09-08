from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen

from binario_marketing.portfolio_inbox_refresh import (
    MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES,
    PORTFOLIO_INBOX_REFRESH_PLAN_SCHEMA,
    PORTFOLIO_INBOX_REFRESH_RESULT_SCHEMA,
    aggregate_refresh_result,
    build_refresh_plan,
    normalize_company_ids,
)
from binario_marketing.service_post_w99_portfolio_inbox_refresh_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class PortfolioInboxRefreshPureTests(unittest.TestCase):
    def test_normalize_requires_exact_unique_bounded_company_ids(self):
        first = "company_" + "1" * 24
        second = "company_" + "2" * 24
        self.assertEqual(normalize_company_ids([first, second]), [first, second])
        with self.assertRaises(ValueError):
            normalize_company_ids([])
        with self.assertRaises(ValueError):
            normalize_company_ids([first, first])
        with self.assertRaises(ValueError):
            normalize_company_ids(["not-a-company"])
        too_many = [f"company_{index:024x}" for index in range(MAX_PORTFOLIO_INBOX_REFRESH_COMPANIES + 1)]
        with self.assertRaises(ValueError):
            normalize_company_ids(too_many)

    def test_plan_excludes_unmapped_and_never_exposes_provider_ids(self):
        mapped = {
            "id": "company_" + "1" * 24,
            "name": "Marca A",
            "facebook_page_id": "provider-page-secretish-id",
            "instagram_id": "provider-instagram-secretish-id",
        }
        unmapped = {
            "id": "company_" + "2" * 24,
            "name": "Marca B",
            "facebook_page_id": None,
            "instagram_id": None,
        }
        plan = build_refresh_plan([unmapped, mapped], {
            mapped["id"]: {
                "snapshot_state": "STALE",
                "captured_at": "2026-09-07T10:00:00+00:00",
                "items": [],
                "refresh_required": True,
            }
        })
        self.assertEqual(plan["schema"], PORTFOLIO_INBOX_REFRESH_PLAN_SCHEMA)
        self.assertEqual(plan["summary"]["configured_companies"], 1)
        self.assertEqual(plan["summary"]["unmapped_companies"], 1)
        self.assertEqual(plan["summary"]["refresh_required"], 1)
        self.assertEqual(plan["company_ids"], [mapped["id"]])
        self.assertEqual(plan["refresh_company_ids"], [mapped["id"]])
        serialized = json.dumps(plan)
        self.assertNotIn("provider-page-secretish-id", serialized)
        self.assertNotIn("provider-instagram-secretish-id", serialized)
        self.assertFalse(plan["safety"]["provider_read_performed"])

    def test_aggregate_preserves_order_and_omits_provider_error_text(self):
        ids = ["company_" + "1" * 24, "company_" + "2" * 24]
        result = aggregate_refresh_result(ids, [
            {"company_id": ids[1], "company_name": "B", "status": "FAILED", "provider_error": "token=do-not-leak"},
            {"company_id": ids[0], "company_name": "A", "status": "REFRESHED", "captured_at": "2026-09-07T12:00:00+00:00", "attention_candidates": 3},
        ])
        self.assertEqual(result["schema"], PORTFOLIO_INBOX_REFRESH_RESULT_SCHEMA)
        self.assertEqual([row["company_id"] for row in result["companies"]], ids)
        self.assertEqual(result["summary"], {"requested": 2, "refreshed": 1, "failed": 1})
        self.assertNotIn("do-not-leak", json.dumps(result))
        self.assertTrue(result["contracts"]["per_company_failure_isolated"])
        self.assertFalse(result["safety"]["provider_mutation_performed"])


class PortfolioInboxRefreshRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.first = self.runtime.companies.create("Marca Uno")
        self.second = self.runtime.companies.create("Marca Dos")
        self.unmapped = self.runtime.companies.create("Sin Meta")
        self.first = self.runtime.companies.update(self.first.id, {"facebook_page_id": "page_one"})
        self.second = self.runtime.companies.update(self.second.id, {"instagram_id": "ig_two"})

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown(); self.tmp.cleanup()

    def test_plan_is_local_and_lists_only_configured_active_companies(self):
        plan = self.runtime.portfolio_inbox_refresh_plan()
        self.assertEqual(plan["summary"]["configured_companies"], 2)
        self.assertEqual(plan["summary"]["unmapped_companies"], 1)
        self.assertEqual(set(plan["company_ids"]), {self.first.id, self.second.id})
        self.assertEqual(set(plan["refresh_company_ids"]), {self.first.id, self.second.id})
        self.assertTrue(all(row["snapshot_state"] == "MISSING" for row in plan["companies"]))
        self.assertFalse(plan["safety"]["provider_read_performed"])

    def test_batch_is_sequential_failure_isolated_and_returns_aggregate_only(self):
        calls = []
        before_activities = list(self.runtime.crm.list_activities(self.first.id))

        def fake_refresh(company_id):
            calls.append(company_id)
            if company_id == self.second.id:
                raise RuntimeError("provider conversation id 123 should never leak")
            return {
                "configured": True,
                "conversations": [{"messages": [{"message": "private body"}]}],
                "attention_snapshot": {
                    "captured_at": "2026-09-07T13:00:00+00:00",
                    "attention_candidates": 4,
                },
            }

        self.runtime.refresh_inbox_attention = fake_refresh
        result = self.runtime.refresh_portfolio_inbox_attention({"company_ids": [self.first.id, self.second.id]})
        self.assertEqual(calls, [self.first.id, self.second.id])
        self.assertEqual(result["summary"], {"requested": 2, "refreshed": 1, "failed": 1})
        serialized = json.dumps(result)
        self.assertNotIn("private body", serialized)
        self.assertNotIn("conversation id", serialized)
        self.assertEqual(list(self.runtime.crm.list_activities(self.first.id)), before_activities)
        self.assertFalse(result["safety"]["reply_performed"])
        self.assertFalse(result["safety"]["crm_mutation_performed"])

    def test_server_revalidates_mapping_before_any_provider_read(self):
        calls = []
        self.runtime.refresh_inbox_attention = lambda company_id: calls.append(company_id)
        with self.assertRaises(ValueError):
            self.runtime.refresh_portfolio_inbox_attention({"company_ids": [self.unmapped.id]})
        self.assertEqual(calls, [])

    def test_http_plan_post_and_static_asset(self):
        calls = []

        def fake_refresh(company_id):
            calls.append(company_id)
            return {"attention_snapshot": {"captured_at": "2026-09-07T14:00:00+00:00", "attention_candidates": 1}}

        self.runtime.refresh_inbox_attention = fake_refresh
        server = create_server(self.runtime, "127.0.0.1", 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            root = f"http://127.0.0.1:{server.server_address[1]}"
            with urlopen(root + "/api/portfolio/inbox-refresh-plan", timeout=5) as response:
                plan = json.loads(response.read().decode("utf-8"))
            self.assertEqual(plan["summary"]["configured_companies"], 2)
            self.assertEqual(set(plan["refresh_company_ids"]), {self.first.id, self.second.id})
            with urlopen(root + "/portfolio-inbox-refresh.js", timeout=5) as response:
                source = response.read().decode("utf-8")
            self.assertIn("POST_W99_PORTFOLIO_INBOX_REFRESH", source)
            body = json.dumps({"company_ids": [self.first.id, self.second.id]}).encode("utf-8")
            request = Request(root + "/api/portfolio/inbox-refresh", data=body, method="POST", headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                result = json.loads(response.read().decode("utf-8"))
            self.assertEqual(result["summary"]["refreshed"], 2)
            self.assertEqual(calls, [self.first.id, self.second.id])
        finally:
            server.shutdown(); thread.join(timeout=5); server.server_close()

    def test_browser_contract_is_explicit_no_polling_and_exact_company_list(self):
        source = (ROOT / "web" / "portfolio-inbox-refresh.js").read_text(encoding="utf-8")
        for required in (
            "Actualizar Inbox pendiente", "window.confirm", "/api/portfolio/inbox-refresh-plan",
            "/api/portfolio/inbox-refresh", "refresh_company_ids", "company_ids:ids", "method:'POST'",
            "no responde mensajes", "Las bandejas vigentes se omiten", "todayPortfolioLoad(true)",
        ):
            self.assertIn(required, source)
        self.assertEqual(source.count("method:'POST'"), 1)
        for forbidden in ("setInterval(", "setTimeout(", "MutationObserver", "sendBeacon", "fetch('https://", 'fetch("https://'):
            self.assertNotIn(forbidden, source)

    def test_source_workflow_and_frozen_release_contract(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_portfolio_inbox_refresh_app", dev)
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_inbox_refresh_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_ai_human_feedback_context_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        docs = (ROOT / "docs" / "POST_W99_PORTFOLIO_INBOX_REFRESH.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)
        self.assertIn("sin polling", docs.casefold())


if __name__ == "__main__":
    unittest.main()
