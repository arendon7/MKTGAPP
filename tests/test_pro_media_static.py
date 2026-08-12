import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]


class ProMediaStaticTests(unittest.TestCase):
    def test_pro_media_javascript_is_served_under_local_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            runtime = AppRuntime.create(ROOT, Path(tmp) / "data")
            server = create_server(runtime, "127.0.0.1", 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                base = f"http://127.0.0.1:{server.server_address[1]}"
                with urlopen(base + "/pro-media.js", timeout=5) as response:
                    body = response.read().decode("utf-8")
                    self.assertEqual(response.status, 200)
                    self.assertIn("javascript", response.headers.get("Content-Type", ""))
                self.assertIn("ensureActiveProxy", body)
                self.assertIn("overlay_add", body)
                self.assertIn("audio_set", body)
            finally:
                server.shutdown()
                runtime.proxies.shutdown()
                runtime.renders.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
