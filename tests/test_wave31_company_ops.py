import tempfile
import unittest
from pathlib import Path

from binario_marketing.company_store import CompanyStore
from binario_marketing.service_wave31 import AppRuntime


ROOT = Path(__file__).resolve().parents[1]


class CompanyStoreTests(unittest.TestCase):
    def test_company_registry_is_durable_and_contains_no_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = CompanyStore(root)
            company = store.create("Greenatics")
            self.assertTrue(company.id.startswith("company_"))
            self.assertEqual(company.slug, "greenatics")
            updated = store.update(company.id, {
                "facebook_page_id": "page-1",
                "facebook_page_name": "Greenatics",
                "instagram_id": "ig-1",
                "instagram_username": "greenatics",
                "ad_account_id": "act-1",
            })
            reopened = CompanyStore(root).get(company.id)
            self.assertEqual(reopened, updated)
            text = (root / f"{company.id}.json").read_text(encoding="utf-8").lower()
            for forbidden in ("access_token", "client_secret", "password", "authorization"):
                self.assertNotIn(forbidden, text)

    def test_company_update_rejects_unknown_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CompanyStore(Path(tmp))
            company = store.create("Sistema Binario")
            with self.assertRaisesRegex(ValueError, "unsupported company fields"):
                store.update(company.id, {"token": "secret"})


class MarketingOpsRuntimeTests(unittest.TestCase):
    def make_runtime(self, tmp: str) -> AppRuntime:
        return AppRuntime.create(ROOT, Path(tmp) / "data")

    @staticmethod
    def shutdown(runtime: AppRuntime) -> None:
        if runtime.social_scheduler is not None:
            runtime.social_scheduler.shutdown()
        runtime.proxies.shutdown()
        runtime.transcriptions.shutdown()
        runtime.renders.shutdown()

    def test_company_publications_do_not_require_or_create_video_projects(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(tmp)
            try:
                before = len(runtime.projects.list_projects())
                company = runtime.create_company({"name": "Greenatics"})
                runtime.update_company(company["id"], {
                    "facebook_page_id": "page-greenatics",
                    "facebook_page_name": "Greenatics",
                })
                row = runtime.create_company_publication(company["id"], {
                    "channel": "facebook_page",
                    "kind": "text",
                    "message": "Transformar residuos en vida",
                })
                self.assertEqual(row["project_id"], company["id"])
                self.assertEqual(row["target_id"], "page-greenatics")
                self.assertEqual(len(runtime.projects.list_projects()), before)
            finally:
                self.shutdown(runtime)

    def test_calendar_and_dashboard_are_company_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(tmp)
            try:
                first = runtime.create_company({"name": "Greenatics"})
                second = runtime.create_company({"name": "Sistema Binario"})
                runtime.update_company(first["id"], {"facebook_page_id": "page-1"})
                runtime.update_company(second["id"], {"facebook_page_id": "page-2"})
                runtime.create_company_publication(first["id"], {
                    "channel": "facebook_page",
                    "kind": "text",
                    "message": "Primera empresa",
                    "scheduled_for": "2030-01-02T12:00:00+00:00",
                })
                runtime.create_company_publication(second["id"], {
                    "channel": "facebook_page",
                    "kind": "text",
                    "message": "Segunda empresa",
                    "scheduled_for": "2030-01-03T12:00:00+00:00",
                })
                all_rows = runtime.ops_calendar()
                first_rows = runtime.ops_calendar(first["id"])
                self.assertEqual(len(all_rows), 2)
                self.assertEqual(len(first_rows), 1)
                self.assertEqual(first_rows[0]["company_name"], "Greenatics")
                dashboard = runtime.ops_dashboard(first["id"])
                self.assertEqual(dashboard["company_count"], 1)
                self.assertEqual(dashboard["summary"]["queued"], 1)
                self.assertEqual(len(dashboard["upcoming"]), 1)
            finally:
                self.shutdown(runtime)

    def test_company_publication_rejects_project_media_coupling(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = self.make_runtime(tmp)
            try:
                company = runtime.create_company({"name": "ProFit"})
                runtime.update_company(company["id"], {"instagram_id": "ig-profit"})
                with self.assertRaisesRegex(ValueError, "Content/Video Studio"):
                    runtime.create_company_publication(company["id"], {
                        "channel": "instagram",
                        "kind": "reel",
                        "message": "Video",
                        "render_id": "render-1",
                    })
            finally:
                self.shutdown(runtime)


if __name__ == "__main__":
    unittest.main()
