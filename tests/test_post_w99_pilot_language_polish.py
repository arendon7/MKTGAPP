from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import urlopen

from binario_marketing.service_post_w99_pilot_language_polish_app import AppRuntime, create_server


ROOT = Path(__file__).resolve().parents[1]
FROZEN_MAIN = "60ef38aa01c841c60f98b7dc79fcc9bb5d676e53"


class PilotLanguagePolishTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runtime = AppRuntime.create(ROOT, Path(self.tmp.name) / "data")
        self.server = create_server(self.runtime, "127.0.0.1", 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.root = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()
        if self.runtime.social_scheduler is not None:
            self.runtime.social_scheduler.shutdown()
        self.runtime.proxies.shutdown()
        self.runtime.transcriptions.shutdown()
        self.runtime.renders.shutdown()
        self.tmp.cleanup()

    def test_http_chain_appends_language_adapter_after_session_status(self):
        with urlopen(self.root + "/pilot-session-status.js", timeout=5) as response:
            chained = response.read().decode("utf-8")
        self.assertIn("/pilot-language-polish.js", chained)
        with urlopen(self.root + "/pilot-language-polish.js", timeout=5) as response:
            source = response.read().decode("utf-8")
        self.assertIn("POST_W99_PILOT_LANGUAGE_POLISH", source)
        self.assertIn("MERCADEO APP · Centro de operaciones", source)

    def test_adapter_is_presentation_only_and_has_no_network_or_business_authority(self):
        source = (ROOT / "web" / "pilot-language-polish.js").read_text(encoding="utf-8")
        self.assertIn("Mensajes", source)
        self.assertIn("Panel ejecutivo", source)
        self.assertIn("Centro de acciones", source)
        self.assertIn("fuentes de datos disponibles", source)
        self.assertIn("Crear respaldo verificado", source)
        self.assertIn("PREPARACIÓN PROM.", source)
        self.assertIn("Siguiente acción recomendada", source)
        for forbidden in (
            "fetch(", "opsApi(", "/api/", "method:'POST'", "method:'PATCH'", "method:'DELETE'",
            "setInterval(", "MutationObserver", "localStorage", "opsShowView", "MetaGraphClient",
            "AIProviderClient", "publish-now", "create_campaign", "verify_snapshot(",
        ):
            self.assertNotIn(forbidden, source)

    def test_user_facing_replacements_remove_engineering_terms_without_changing_internal_authority(self):
        source = (ROOT / "web" / "pilot-language-polish.js").read_text(encoding="utf-8")
        # Engineering terms may remain as exact source strings solely so the presentation adapter can replace them.
        self.assertIn("No se pudo leer el estado de preparación de esta empresa.", source)
        self.assertIn("Los pasos de preparación de la empresa están completos.", source)
        self.assertIn("Los pasos y porcentajes reflejan la preparación de cada empresa.", source)
        self.assertIn("La preparación de cada empresa se revisa desde Empresas.", source)
        self.assertIn("['PROMEDIO READINESS','PREPARACIÓN PROM.']", source)
        self.assertNotIn("W50 conserva", source)
        self.assertNotIn("Command Center/W50", source)

    def test_terminal_release_separation_and_documentation(self):
        workflows = sorted(path.name for path in (ROOT / ".github" / "workflows").glob("*.yml"))
        self.assertEqual(workflows, ["ci.yml", "full-mac-app.yml", "persistent-release.yml"])
        service = (ROOT / "src" / "binario_marketing" / "service_post_w99_pilot_language_polish_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_session_status_app as base", service)
        self.assertNotIn("MetaGraphClient", service)
        self.assertNotIn("AIProviderClient", service)
        dev = (ROOT / "src" / "binario_marketing" / "service_post_w99_dev_app.py").read_text(encoding="utf-8")
        self.assertIn("service_post_w99_pilot_language_polish_app", dev)
        docs = (ROOT / "docs" / "POST_W99_PILOT_LANGUAGE_POLISH.md").read_text(encoding="utf-8")
        self.assertIn(FROZEN_MAIN, docs)
        self.assertIn("not production", docs.casefold())
        self.assertIn("w50", docs.casefold())
        self.assertIn("presentation", docs.casefold())


if __name__ == "__main__":
    unittest.main()
