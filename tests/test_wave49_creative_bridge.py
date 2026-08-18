import base64
import hashlib
import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from binario_marketing.render_queue import RenderRecord
from binario_marketing.service_wave49_app import AppRuntime

ROOT = Path(__file__).resolve().parents[1]
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Y9Z5mEAAAAASUVORK5CYII=")


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class Wave49CreativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.company = self.runtime.create_company({"name": "Greenatics"})
        self.workspace = self.runtime.ensure_company_workspace(self.company["id"])
        self.project_id = self.workspace["project_id"]

    def tearDown(self):
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown(); self.runtime.transcriptions.shutdown(); self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def fake_render(self, job_id: str, payload: bytes = b"fake-mp4-content") -> RenderRecord:
        output_name = f"{job_id}-social.mp4"
        output = self.runtime.projects.export_path(self.project_id, output_name)
        output.write_bytes(payload)
        now = datetime.now(timezone.utc).isoformat()
        record = RenderRecord(
            id=job_id,
            project_id=self.project_id,
            asset_id="f" * 12,
            output_name=output_name,
            output_relative_path=f"exports/{output_name}",
            start=0.0,
            end=3.0,
            width=1080,
            height=1920,
            status="PASS",
            progress=1.0,
            created_at=now,
            updated_at=now,
            sha256=sha(payload),
            bytes=len(payload),
            source_asset_ids=["f" * 12],
        )
        self.runtime.renders._replace(record)
        return record

    def test_render_promotion_is_idempotent_and_preserves_probe(self):
        render = self.fake_render("a" * 12)
        first = self.runtime.promote_company_creative(self.company["id"], {"source_type": "render", "source_id": render.id})
        second = self.runtime.promote_company_creative(self.company["id"], {"source_type": "render", "source_id": render.id})
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(first["media"]["id"], second["media"]["id"])
        self.assertEqual(first["bridge"]["id"], second["bridge"]["id"])
        self.assertEqual(first["media"]["sha256"], render.sha256)
        self.assertEqual(first["media"]["width"], 1080)
        self.assertEqual(first["media"]["height"], 1920)
        self.assertEqual(first["media"]["duration"], 3.0)

    def test_different_render_same_sha_reuses_company_media_but_keeps_lineage(self):
        first_render = self.fake_render("a" * 12, b"same-output")
        second_render = self.fake_render("b" * 12, b"same-output")
        first = self.runtime.promote_company_creative(self.company["id"], {"source_type": "render", "source_id": first_render.id})
        second = self.runtime.promote_company_creative(self.company["id"], {"source_type": "render", "source_id": second_render.id})
        self.assertTrue(second["reused"])
        self.assertEqual(first["media"]["id"], second["media"]["id"])
        self.assertNotEqual(first["bridge"]["id"], second["bridge"]["id"])
        self.assertEqual(len(self.runtime.company_media.list(self.company["id"])), 1)
        self.assertEqual(len(self.runtime.creative_bridge.list(self.company["id"])), 2)

    def test_render_tamper_blocks_promotion(self):
        render = self.fake_render("c" * 12, b"certified")
        self.runtime.renders.output_path(render.id).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError, "SHA-256|size"):
            self.runtime.promote_company_creative(self.company["id"], {"source_type": "render", "source_id": render.id})
        self.assertEqual(self.runtime.company_media.list(self.company["id"]), [])

    def test_project_asset_can_promote_to_company_library(self):
        asset = self.runtime.projects.add_uploaded_asset(self.project_id, "creative.png", "image", io.BytesIO(PNG), len(PNG))
        result = self.runtime.promote_company_creative(self.company["id"], {"source_type": "project_asset", "source_id": asset.id})
        self.assertEqual(result["media"]["kind"], "image")
        self.assertEqual(result["media"]["sha256"], asset.sha256)
        self.assertEqual(result["bridge"]["source_type"], "project_asset")

    def test_campaign_attachment_is_idempotent_and_company_scoped(self):
        asset = self.runtime.projects.add_uploaded_asset(self.project_id, "creative.png", "image", io.BytesIO(PNG), len(PNG))
        media = self.runtime.promote_company_creative(self.company["id"], {"source_type": "project_asset", "source_id": asset.id})["media"]
        campaign = self.runtime.create_campaign(self.company["id"], {"name": "Campaña", "objective": "LEADS"})
        first = self.runtime.attach_company_media_to_campaign(self.company["id"], media["id"], campaign["id"])
        second = self.runtime.attach_company_media_to_campaign(self.company["id"], media["id"], campaign["id"])
        self.assertTrue(first["changed"])
        self.assertFalse(second["changed"])
        self.assertEqual(second["campaign"]["media_ids"].count(media["id"]), 1)
        other = self.runtime.create_company({"name": "Otra"})
        other_campaign = self.runtime.create_campaign(other["id"], {"name": "Otra campaña", "objective": "SALES"})
        with self.assertRaises(KeyError):
            self.runtime.attach_company_media_to_campaign(self.company["id"], media["id"], other_campaign["id"])


if __name__ == "__main__":
    unittest.main()
