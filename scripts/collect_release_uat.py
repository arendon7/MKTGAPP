#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.release-uat-evidence.v1"
MANUAL_STEPS = (
    ("launcher_relaunch", "Abrir la app desde Finder/LaunchServices, cerrarla y reabrirla sin Terminal."),
    ("persistence", "Crear/editar datos y confirmar persistencia después de reiniciar la app."),
    ("company_crm", "Crear empresa/contacto/seguimiento y validar CRM."),
    ("today_complete", "Completar un seguimiento desde HOY · PRIORIDADES y confirmar que desaparece como pendiente."),
    ("today_reschedule", "Reprogramar un seguimiento desde HOY · PRIORIDADES a una fecha futura y confirmar trazabilidad."),
    ("content_library", "Importar/gestionar contenido de empresa y comprobar acceso posterior."),
    ("social_readonly", "Refrescar analítica/inbox social de forma explícita y comprobar que no existe polling automático."),
    ("manual_reply", "Enviar una respuesta social únicamente mediante la acción manual y confirmación prevista."),
    ("editorial_management", "Corregir/reprogramar/cancelar una publicación usando Gestión Editorial con confirmaciones."),
    ("video_import_render", "Importar video real, editar y producir un render reproducible que se pueda abrir."),
    ("transcription", "Transcribir audio/video real con el runtime Whisper embebido."),
    ("credentials", "Configurar/probar credenciales y confirmar que permanecen en Keychain, no en archivos del proyecto."),
)


def _run(cmd: list[str]) -> dict[str, Any]:
    try:
        cp = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=False)
        return {"ok": cp.returncode == 0, "returncode": cp.returncode, "stdout": (cp.stdout or "")[-4000:], "stderr": (cp.stderr or "")[-4000:]}
    except Exception as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": f"{type(exc).__name__}: {exc}"}


def _json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected object: {path}")
    return data


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# BINARIO Marketing IA · Physical UAT Evidence",
        "",
        f"- Generated: `{report['generated_at']}`",
        f"- Git SHA: `{report['git_sha']}`",
        f"- Architecture: `{report['architecture']}`",
        f"- Version: `{report['version']}`",
        f"- Overall: **{report['overall']}**",
        "",
        "## Automatic checks",
    ]
    for row in report["automatic_checks"]:
        lines.append(f"- **{'PASS' if row['ok'] else 'FAIL'}** · {row['name']}")
    lines += ["", "## Manual gates"]
    for row in report["manual_steps"]:
        lines.append(f"- **{row['status']}** · `{row['id']}` — {row['step']}")
    lines += [
        "",
        "## Rule",
        "",
        "Este archivo se genera inicialmente con `uat_passed=false`. UAT solo puede considerarse PASS cuando todos los gates manuales se ejecuten sobre este mismo SHA/arquitectura y la evidencia final se registre explícitamente.",
        "La generación del reporte no habilita `RELEASE_READY`, no crea un tag y no sustituye firma Developer ID ni notarización.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect physical release UAT evidence for one exact BINARIO Marketing Mac candidate.")
    ap.add_argument("--app", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()

    app = args.app.expanduser().resolve()
    resources = app / "Contents" / "Resources"
    provenance = _json(resources / "BUILD_PROVENANCE.json")
    readiness = _json(resources / "RELEASE_READINESS.json")

    codesign = _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)])
    launch_executable = app / "Contents" / "MacOS" / "Binario Marketing IA"
    checks = [
        {"name": "build_provenance", "ok": provenance.get("git_sha") == readiness.get("git_sha") and bool(provenance.get("git_sha"))},
        {"name": "architecture", "ok": provenance.get("architecture") in {"arm64", "x86_64"}, "value": provenance.get("architecture")},
        {"name": "codesign_integrity", "ok": codesign["ok"], "detail": codesign},
        {"name": "launcher_present", "ok": launch_executable.is_file()},
        {"name": "engineering_readiness_present", "ok": readiness.get("schema") == "binario.marketing.release-readiness.v1"},
    ]
    automatic_ok = all(row["ok"] for row in checks)
    manual = [{"id": key, "status": "PENDING", "step": text} for key, text in MANUAL_STEPS]
    report = {
        "schema": SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {"system": platform.system(), "release": platform.release(), "machine": platform.machine()},
        "app": str(app),
        "git_sha": provenance.get("git_sha"),
        "architecture": provenance.get("architecture"),
        "version": provenance.get("product_version"),
        "signing_mode": provenance.get("signing_mode"),
        "notarized": provenance.get("notarized"),
        "automatic_checks": checks,
        "manual_steps": manual,
        "automatic_passed": automatic_ok,
        "uat_passed": False,
        "overall": "AUTOMATIC_FAIL" if not automatic_ok else "AUTOMATIC_PASS_MANUAL_PENDING",
    }

    out = args.output.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "release-uat-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "release-uat-evidence.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "output": str(out), "git_sha": report["git_sha"], "architecture": report["architecture"]}, ensure_ascii=False, indent=2))
    return 0 if automatic_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
