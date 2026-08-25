from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_serve_dev_advances_only_to_evidence_observability_terminal():
    dev = (ROOT / "src/binario_marketing/service_post_w99_dev_app.py").read_text(encoding="utf-8")
    cli = (ROOT / "src/binario_marketing/cli.py").read_text(encoding="utf-8")
    version = (ROOT / "src/binario_marketing/version.py").read_text(encoding="utf-8")
    service = (ROOT / "src/binario_marketing/service.py").read_text(encoding="utf-8")

    assert "service_post_w99_evidence_observability_app" in dev
    assert "service_post_w99_today_execution_app" not in dev
    assert "service_post_w99_dev_app" in cli
    assert 'RELEASE_TAG: str | None = "v0.9.0"' in version
    assert "RELEASE_READY = True" in version
    assert "service_post_w99_evidence_observability_app" not in service
