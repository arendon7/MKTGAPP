#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "binario.marketing.release-uat-evidence.v1"
CANDIDATE_SCHEMA = "binario.marketing.physical-uat-candidate.v1"
PHYSICAL_ROLE = "PHYSICAL_UAT_CANDIDATE_ONLY"
SOURCE_CONTRACT_WAVE = 94
LOCKED_SOURCE = "LOCKED_SOURCE"
PREPARED_RELEASE = "PREPARED_RELEASE"
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_contract(candidate: dict[str, Any]) -> tuple[str | None, str | None, bool]:
    boundary = candidate.get("release_boundary") if isinstance(candidate.get("release_boundary"), dict) else {}
    version = str(candidate.get("product_version") or "")
    state = candidate.get("source_release_state") or boundary.get("source_release_state")
    ready = boundary.get("release_ready")
    tag = boundary.get("release_tag")
    authority_clear = (
        boundary.get("operational_authorization") in {None, False}
        and boundary.get("release_authority") in {None, False}
        and boundary.get("publication_authority") in {None, False}
        and boundary.get("production_ready") is False
    )
    if state is None and ready is False and tag is None:
        state = LOCKED_SOURCE
    if state == LOCKED_SOURCE:
        valid = ready is False and tag is None and authority_clear
    elif state == PREPARED_RELEASE:
        valid = ready is True and tag == f"v{version}" and ".dev" not in version.lower() and "rc" not in version.lower() and authority_clear
    else:
        valid = False
    return str(state) if state is not None else None, str(tag) if tag is not None else None, valid


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# BINARIO Marketing IA · Physical UAT Evidence", "",
        f"- Generated: `{report['generated_at']}`",
        f"- Git SHA: `{report['git_sha']}`",
        f"- Candidate source SHA-256: `{report['candidate_source_sha256']}`",
        f"- Architecture: `{report['architecture']}`",
        f"- Version: `{report['version']}`",
        f"- Source contract: `Wave {report.get('source_contract_wave')}`",
        f"- Source release state: `{report.get('source_release_state')}`",
        f"- Prepared release tag: `{report.get('source_release_tag')}`",
        f"- Overall: **{report['overall']}**", "", "## Automatic checks",
    ]
    for row in report["automatic_checks"]:
        lines.append(f"- **{'PASS' if row['ok'] else 'FAIL'}** · {row['name']}")
    lines += ["", "## Manual gates"]
    for row in report["manual_steps"]:
        lines.append(f"- **{row['status']}** · `{row['id']}` — {row['step']}")
    lines += [
        "", "## Rule", "",
        "Este archivo se genera inicialmente con `uat_passed=false`. UAT solo puede considerarse PASS cuando todos los gates manuales se ejecuten sobre este mismo SHA, digest de fuente, estado de release de fuente y candidato arm64 generado desde main.",
        "`PREPARED_RELEASE` significa únicamente que versión/tag quedaron congelados antes de UAT; no concede autoridad de release, firma Developer ID, notarización ni publicación.",
        "La generación del reporte no crea un tag y no sustituye firma Developer ID ni notarización.", "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Collect physical release UAT evidence for one exact BINARIO Marketing Mac candidate.")
    ap.add_argument("--app", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    app = args.app.expanduser().resolve(); resources = app / "Contents/Resources"
    provenance = _json(resources / "BUILD_PROVENANCE.json"); readiness = _json(resources / "RELEASE_READINESS.json")
    candidate_path = resources / "PHYSICAL_UAT_CANDIDATE.json"; candidate = _json(candidate_path) if candidate_path.is_file() else {}
    codesign = _run(["/usr/bin/codesign", "--verify", "--deep", "--strict", str(app)]); launch_executable = app / "Contents/MacOS/Binario Marketing IA"
    host_system = platform.system(); host_machine = platform.machine().lower(); is_ci = os.environ.get("GITHUB_ACTIONS") == "true" or os.environ.get("CI") == "true"
    origin = candidate.get("build_origin") if isinstance(candidate.get("build_origin"), dict) else {}; ref = str(origin.get("ref") or "")
    source_state, source_tag, source_contract_valid = _source_contract(candidate)
    source_contract_wave = candidate.get("source_contract_wave")
    trusted_origin = bool(
        candidate.get("role") == PHYSICAL_ROLE
        and origin.get("event") == "push"
        and ref == "refs/heads/main"
        and origin.get("trusted_for_physical_uat") is True
        and candidate.get("physical_uat", {}).get("eligible_build_origin") is True
    )
    candidate_consistent = bool(
        candidate.get("schema") == CANDIDATE_SCHEMA
        and trusted_origin
        and source_contract_valid
        and source_contract_wave == SOURCE_CONTRACT_WAVE
        and candidate.get("git_sha") == provenance.get("git_sha")
        and candidate.get("architecture") == provenance.get("architecture") == "arm64"
        and candidate.get("product_version") == provenance.get("product_version")
        and isinstance(candidate.get("candidate_source_sha256"), str)
        and len(candidate.get("candidate_source_sha256")) == 64
        and candidate.get("runtime_wave") == 76
        and candidate.get("certification_guard_wave") == 84
        and candidate.get("physical_uat", {}).get("automatic_pass") is False
    )
    physical_host = host_system == "Darwin" and host_machine == "arm64" and not is_ci
    checks = [
        {"name": "build_provenance", "ok": provenance.get("git_sha") == readiness.get("git_sha") and bool(provenance.get("git_sha"))},
        {"name": "physical_arm64_candidate", "ok": provenance.get("architecture") == "arm64", "value": provenance.get("architecture")},
        {"name": "physical_arm64_host", "ok": physical_host, "value": {"system": host_system, "machine": host_machine, "is_ci": is_ci}},
        {"name": "trusted_build_origin", "ok": trusted_origin, "value": {"role": candidate.get("role"), "origin": origin}},
        {"name": "source_release_contract", "ok": source_contract_valid and source_contract_wave == SOURCE_CONTRACT_WAVE, "value": {"wave": source_contract_wave, "state": source_state, "tag": source_tag}},
        {"name": "candidate_manifest", "ok": candidate_consistent, "value": candidate.get("schema")},
        {"name": "codesign_integrity", "ok": codesign["ok"], "detail": codesign},
        {"name": "launcher_present", "ok": launch_executable.is_file()},
        {"name": "engineering_readiness_present", "ok": readiness.get("schema") == "binario.marketing.release-readiness.v1"},
    ]
    automatic_ok = all(row["ok"] for row in checks); manual = [{"id": key, "status": "PENDING", "step": text} for key, text in MANUAL_STEPS]
    report = {
        "schema": SCHEMA, "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": {"system": host_system, "release": platform.release(), "machine": host_machine, "is_ci": is_ci},
        "app": str(app), "git_sha": provenance.get("git_sha"), "architecture": provenance.get("architecture"), "version": provenance.get("product_version"),
        "source_contract_wave": source_contract_wave, "source_release_state": source_state, "source_release_tag": source_tag,
        "candidate_schema": candidate.get("schema"), "candidate_role": candidate.get("role"), "candidate_build_origin": origin,
        "candidate_source_sha256": candidate.get("candidate_source_sha256"), "candidate_manifest_sha256": _sha256(candidate_path) if candidate_path.is_file() else None,
        "runtime_wave": candidate.get("runtime_wave"), "signing_mode": provenance.get("signing_mode"), "notarized": provenance.get("notarized"),
        "automatic_checks": checks, "manual_steps": manual, "automatic_passed": automatic_ok, "uat_passed": False,
        "overall": "AUTOMATIC_FAIL" if not automatic_ok else "AUTOMATIC_PASS_MANUAL_PENDING",
        "release_authority": False, "publication_authority": False, "production_ready": False,
    }
    out = args.output.expanduser().resolve(); out.mkdir(parents=True, exist_ok=True)
    (out / "release-uat-evidence.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out / "release-uat-evidence.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"overall": report["overall"], "output": str(out), "git_sha": report["git_sha"], "candidate_source_sha256": report["candidate_source_sha256"], "source_contract_wave": source_contract_wave, "source_release_state": source_state, "source_release_tag": source_tag, "architecture": report["architecture"]}, ensure_ascii=False, indent=2))
    return 0 if automatic_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
