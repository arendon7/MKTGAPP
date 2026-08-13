import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from binario_marketing import meta_graph
from binario_marketing.meta_credentials import MetaCredentialStore
from binario_marketing.meta_graph import MetaGraphError
from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


def request_json(url, *, method="GET", payload=None):
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, method=method, headers=headers)
    with urlopen(request, timeout=5) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class Wave23ExtensionHttpApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.secret_file = root / "meta-secret"
        self.helper = root / "meta-keychain-helper"
        secret_path = str(self.secret_file).replace("'", "'\\''")
        self.helper.write_text(
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            f"STORE='{secret_path}'\n"
            "case \"${1:-status}\" in\n"
            "  get) [[ -f \"$STORE\" ]] || exit 3; cat \"$STORE\" ;;\n"
            "  set) cat > \"$STORE\"; printf 'ok\\n' ;;\n"
            "  delete) rm -f \"$STORE\"; printf 'ok\\n' ;;\n"
            "  status) [[ -f \"$STORE\" ]] && printf 'configured\\n' || printf 'missing\\n' ;;\n"
            "  *) exit 64 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        self.helper.chmod(0o700)
        self.env = patch.dict(
            os.environ,
            {
                "BINARIO_META_KEYCHAIN_HELPER": str(self.helper),
                "META_ACCESS_TOKEN": "",
                "META_GRAPH_API_VERSION": "v25.0",
            },
            clear=False,
        )
        self.env.start()
        self.runtime = AppRuntime.create(ROOT, root / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.project = self.runtime.create_project("Pauta Wave 23")
        self.project_id = self.project["id"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.env.stop()
        self.tmp.cleanup()

    def test_meta_connection_validates_then_persists_without_echoing_token(self):
        supplied = "test-meta-token-never-echo"

        def transport(method, url, params):
            self.assertEqual(method, "GET")
            self.assertTrue(url.endswith("/me"))
            self.assertEqual(params.get("access_token"), supplied)
            return {"id": "meta-user-1", "name": "Meta Test"}

        with patch.object(meta_graph, "_default_transport", transport):
            status, connected = request_json(
                f"{self.base}/api/meta/connection",
                method="POST",
                payload={"access_token": supplied},
            )
        self.assertEqual(status, 201)
        encoded = json.dumps(connected)
        self.assertNotIn(supplied, encoded)
        self.assertNotIn("access_token", encoded.lower())
        self.assertEqual(connected["identity"]["id"], "meta-user-1")
        self.assertTrue(self.secret_file.is_file())
        self.assertEqual(self.secret_file.read_text(encoding="utf-8"), supplied)

        status, current = request_json(f"{self.base}/api/meta/status")
        self.assertEqual(status, 200)
        self.assertTrue(current["configured"])
        self.assertEqual(current["credential_source"], "keychain")
        self.assertNotIn(supplied, json.dumps(current))

        status, disconnected = request_json(f"{self.base}/api/meta/connection", method="DELETE")
        self.assertEqual(status, 200)
        self.assertFalse(disconnected["configured"])
        self.assertFalse(self.secret_file.exists())

    def _paid_media_payload(self):
        return {
            "ad_account_id": "77",
            "campaign_name": "Agosto tráfico",
            "campaign_objective": "OUTCOME_TRAFFIC",
            "special_ad_categories": [],
            "adset_name": "Colombia 21-55",
            "daily_budget": 2100,
            "optimization_goal": "LINK_CLICKS",
            "targeting": {
                "age_min": 21,
                "age_max": 55,
                "geo_locations": {"countries": ["CO"]},
            },
            "page_id": "page-1",
            "instagram_actor_id": "ig-1",
            "creative_name": "Creative producto",
            "message": "Conoce el producto",
            "link_url": "https://example.com/producto",
            "picture_url": "https://cdn.example.com/producto.jpg",
            "call_to_action": "LEARN_MORE",
            "ad_name": "Ad producto A",
        }

    def test_paid_media_http_draft_list_cancel_is_project_scoped_and_secret_free(self):
        payload = self._paid_media_payload()
        status, row = request_json(
            f"{self.base}/api/projects/{self.project_id}/paid-media",
            method="POST",
            payload=payload,
        )
        self.assertEqual(status, 201)
        self.assertEqual(row["status"], "DRAFT")
        draft_id = row["id"]
        encoded = json.dumps(row).lower()
        self.assertNotIn("access_token", encoded)
        self.assertNotIn('"active"', encoded)

        status, rows = request_json(f"{self.base}/api/projects/{self.project_id}/paid-media")
        self.assertEqual(status, 200)
        self.assertEqual([item["id"] for item in rows], [draft_id])

        status, detail = request_json(f"{self.base}/api/projects/{self.project_id}")
        self.assertEqual(status, 200)
        self.assertEqual(detail["paid_media"][0]["id"], draft_id)

        other = self.runtime.create_project("Otro proyecto")
        request = Request(
            f"{self.base}/api/projects/{other['id']}/paid-media/{draft_id}",
            method="DELETE",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=5)
        self.assertEqual(raised.exception.code, 404)

        status, cancelled = request_json(
            f"{self.base}/api/projects/{self.project_id}/paid-media/{draft_id}",
            method="DELETE",
        )
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["status"], "CANCELLED")

    def test_remote_paid_media_failure_checkpoints_and_retry_does_not_duplicate_campaign(self):
        MetaCredentialStore().write("paid-media-test-token")
        status, row = request_json(
            f"{self.base}/api/projects/{self.project_id}/paid-media",
            method="POST",
            payload=self._paid_media_payload(),
        )
        self.assertEqual(status, 201)
        draft_id = row["id"]
        calls = []
        state = {"fail_adset": True}

        def transport(method, url, params):
            calls.append((method, url, dict(params)))
            if url.endswith("/act_77/campaigns"):
                self.assertEqual(params["status"], "PAUSED")
                return {"id": "campaign-1"}
            if url.endswith("/act_77/adsets"):
                self.assertEqual(params["status"], "PAUSED")
                if state["fail_adset"]:
                    raise MetaGraphError("simulated adset failure")
                return {"id": "adset-1"}
            if url.endswith("/act_77/adcreatives"):
                self.assertNotIn("status", params)
                return {"id": "creative-1"}
            if url.endswith("/act_77/ads"):
                self.assertEqual(params["status"], "PAUSED")
                return {"id": "ad-1"}
            raise AssertionError(f"unexpected Meta call: {method} {url}")

        with patch.object(meta_graph, "_default_transport", transport):
            request = Request(
                f"{self.base}/api/projects/{self.project_id}/paid-media/{draft_id}/create-paused",
                data=b"{}",
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 502)
            failure = json.loads(raised.exception.read().decode("utf-8"))
            self.assertIn("simulated adset failure", failure["error"])

            checkpoint = self.runtime.paid_media.get(draft_id)
            self.assertEqual(checkpoint.status, "DRAFT")
            self.assertEqual(checkpoint.campaign_id, "campaign-1")
            self.assertIsNone(checkpoint.adset_id)

            state["fail_adset"] = False
            status, completed = request_json(
                f"{self.base}/api/projects/{self.project_id}/paid-media/{draft_id}/create-paused",
                method="POST",
                payload={},
            )

        self.assertEqual(status, 201)
        self.assertEqual(completed["status"], "REMOTE_PAUSED")
        self.assertEqual(completed["campaign_id"], "campaign-1")
        self.assertEqual(completed["adset_id"], "adset-1")
        self.assertEqual(completed["creative_id"], "creative-1")
        self.assertEqual(completed["ad_id"], "ad-1")
        campaign_calls = [call for call in calls if call[1].endswith("/act_77/campaigns")]
        self.assertEqual(len(campaign_calls), 1)
        self.assertTrue(all(call[2].get("status") == "PAUSED" for call in calls if call[1].endswith(("/campaigns", "/adsets", "/ads"))))


if __name__ == "__main__":
    unittest.main()
