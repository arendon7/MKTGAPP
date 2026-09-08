from __future__ import annotations

import unittest
from pathlib import Path

from binario_marketing.portfolio_inbox_refresh import build_refresh_plan


ROOT = Path(__file__).resolve().parents[1]


class SelectivePortfolioInboxRefreshTests(unittest.TestCase):
    @staticmethod
    def _company(index: int, name: str) -> dict:
        return {
            "id": f"company_{index:024x}",
            "name": name,
            "facebook_page_id": f"page_{index}",
            "instagram_id": None,
        }

    def test_current_snapshot_is_visible_but_omitted_from_default_provider_batch(self):
        current = self._company(1, "Actual")
        stale = self._company(2, "Pendiente")
        plan = build_refresh_plan([current, stale], {
            current["id"]: {
                "snapshot_state": "CURRENT",
                "captured_at": "2026-09-07T20:00:00+00:00",
                "items": [{"interaction_id": "safe-local-evidence"}],
                "refresh_required": False,
            },
            stale["id"]: {
                "snapshot_state": "STALE",
                "captured_at": "2026-09-07T01:00:00+00:00",
                "items": [],
                "refresh_required": True,
            },
        })
        self.assertEqual(plan["summary"]["configured_companies"], 2)
        self.assertEqual(plan["summary"]["refresh_required"], 1)
        self.assertEqual(plan["summary"]["current"], 1)
        self.assertEqual(plan["refresh_company_ids"], [stale["id"]])
        self.assertIn(current["id"], plan["company_ids"])
        self.assertTrue(plan["contracts"]["default_batch_refresh_required_only"])
        self.assertTrue(plan["contracts"]["current_snapshots_skipped_by_default"])
        self.assertFalse(plan["safety"]["provider_read_performed"])

    def test_pending_rows_sort_before_current_rows_without_changing_provider_authority(self):
        current = self._company(1, "A Actual")
        missing = self._company(2, "Z Pendiente")
        plan = build_refresh_plan([current, missing], {
            current["id"]: {"snapshot_state": "CURRENT", "refresh_required": False, "items": []},
            missing["id"]: {"snapshot_state": "MISSING", "refresh_required": True, "items": []},
        })
        self.assertEqual(plan["companies"][0]["company_id"], missing["id"])
        self.assertEqual(plan["refresh_company_ids"], [missing["id"]])
        self.assertFalse(plan["safety"]["provider_mutation_performed"])
        self.assertFalse(plan["safety"]["automatic"])
        self.assertFalse(plan["safety"]["background_polling"])

    def test_browser_uses_only_selective_ids_and_disables_when_local_inbox_is_current(self):
        source = (ROOT / "web" / "portfolio-inbox-refresh.js").read_text(encoding="utf-8")
        self.assertIn("refresh_company_ids", source)
        self.assertIn("Actualizar Inbox pendiente", source)
        self.assertIn("Inbox al día", source)
        self.assertIn("Las bandejas vigentes se omiten", source)
        self.assertIn("summary.refresh_overflow", source)
        self.assertNotIn("Boolean((state.plan?.summary||{}).eligible_overflow)", source)
        self.assertEqual(source.count("method:'POST'"), 1)
        for forbidden in ("setInterval(", "setTimeout(", "MutationObserver", "sendBeacon"):
            self.assertNotIn(forbidden, source)

    def test_post_authority_and_release_boundary_are_unchanged(self):
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_portfolio_inbox_refresh_app.py").read_text(encoding="utf-8")
        self.assertIn("refresh_portfolio_inbox_attention", service)
        self.assertIn("normalize_company_ids", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        docs = (ROOT / "docs" / "POST_W99_SELECTIVE_PORTFOLIO_INBOX_REFRESH.md").read_text(encoding="utf-8")
        self.assertIn("60ef38aa01c841c60f98b7dc79fcc9bb5d676e53", docs)


if __name__ == "__main__":
    unittest.main()
