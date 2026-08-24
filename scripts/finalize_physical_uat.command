#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
fail(){ printf 'COMBINED PHYSICAL UAT BLOCKED: %s\n' "$1" >&2; exit 4; }

[[ "$(uname -s)" == "Darwin" ]] || fail "finalization must run on macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "finalization requires the Apple Silicon physical-UAT host"
[[ "${GITHUB_ACTIONS:-}" != "true" && "${CI:-}" != "true" ]] || fail "physical UAT cannot be finalized in CI"

APP="$ROOT/PHYSICAL_UAT_WORK/Binario Marketing IA.app"
PY="$APP/Contents/Resources/runtime/python/bin/python3"
FINALIZER="$ROOT/FINALIZE_PHYSICAL_UAT.py"
VERIFY="$ROOT/PHYSICAL_UAT_HANDOFF_VERIFY.py"
PHASE_B="$ROOT/PHYSICAL_UAT_EVIDENCE/release-uat-evidence.json"
VERIFY_REPORT="$ROOT/PHYSICAL_UAT_EVIDENCE/PHYSICAL_UAT_HANDOFF_VERIFICATION.json"
OUT="$ROOT/PHYSICAL_UAT_EVIDENCE/combined"
ATTESTATION="$OUT/combined-physical-uat-attestation.json"
SUMMARY="$OUT/combined-physical-uat-attestation.md"

[[ -d "$APP" ]] || fail "candidate app not found; run START_PHYSICAL_UAT.command first"
[[ -x "$PY" ]] || fail "embedded Python runtime missing"
[[ -f "$FINALIZER" ]] || fail "combined-UAT finalizer missing"
[[ -f "$VERIFY" ]] || fail "handoff verifier missing"
[[ -f "$PHASE_B" ]] || fail "Phase B evidence missing; complete RECORD_RELEASE_UAT.command first"

PHASE_A="${1:-}"
if [[ -z "$PHASE_A" ]]; then
  PHASE_A="$(/usr/bin/osascript <<'APPLESCRIPT'
try
  set chosenFile to choose file with prompt "Seleccione el JSON de evidencia Fase A descargado desde Release Evidence"
  return POSIX path of chosenFile
on error number -128
  return ""
end try
APPLESCRIPT
)"
fi
[[ -n "$PHASE_A" && -f "$PHASE_A" ]] || fail "Phase A evidence JSON was not selected"

# W97 closes the post-START integrity window. Before the legacy W85 finalizer
# runs, revalidate both bundle signature and the exact extracted source.
/usr/bin/codesign --verify --deep --strict "$APP" || fail "candidate bundle signature drift detected"
"$PY" -I -B "$VERIFY" --delivery-dir "$ROOT" --app "$APP" --require-physical-host > "$VERIFY_REPORT"

mkdir -p "$OUT"
"$PY" -I -B "$FINALIZER" \
  --app "$APP" \
  --phase-a "$PHASE_A" \
  --phase-b "$PHASE_B" \
  --output "$OUT"

[[ -f "$ATTESTATION" ]] || fail "combined attestation was not created"
[[ -f "$SUMMARY" ]] || fail "combined attestation summary was not created"

# Defense in depth: the finalizer can also be invoked directly, so immediately
# before the release-transportable attestation is sealed, re-run codesign and
# bind the final W97 handoff report into the attestation digest itself.
/usr/bin/codesign --verify --deep --strict "$APP" || fail "candidate bundle signature drift detected before final seal"
"$PY" -I -B - "$VERIFY_REPORT" "$ATTESTATION" "$SUMMARY" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

verify_path, attestation_path, summary_path = map(Path, sys.argv[1:4])


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"W97 FINAL INTEGRITY BLOCKED: expected JSON object: {path}")
    return data


def digest(payload):
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def require(ok, message):
    if not ok:
        raise SystemExit(f"W97 FINAL INTEGRITY BLOCKED: {message}")


handoff = load(verify_path)
attestation = load(attestation_path)
binding = attestation.get("binding") or {}
require(isinstance(binding, dict), "combined binding missing")
require(handoff.get("schema") == "binario.marketing.physical-uat-handoff-verification.v3", "final handoff schema drift")
require(handoff.get("role") == "PHYSICAL_UAT_CANDIDATE_ONLY", "final handoff is not the physical candidate")
require(handoff.get("physical_uat_eligible") is True, "final handoff is not physically eligible")
require(handoff.get("git_sha") == binding.get("git_sha"), "final handoff git SHA mismatch")
require(handoff.get("architecture") == binding.get("architecture") == "arm64", "final handoff architecture mismatch")
require(handoff.get("runtime_wave") == binding.get("runtime_wave") == 76, "final handoff runtime wave mismatch")
require(handoff.get("source_contract_wave") == binding.get("source_contract_wave") == 95, "final handoff source contract mismatch")
require(handoff.get("source_release_state") == binding.get("source_release_state") == "PREPARED_RELEASE", "final handoff source state mismatch")
require(handoff.get("source_release_tag") == binding.get("source_release_tag") == "v0.9.0", "final handoff release tag mismatch")
require(handoff.get("candidate_source_sha256") == binding.get("candidate_source_sha256"), "final handoff source digest mismatch")
require(handoff.get("actual_candidate_source_sha256") == binding.get("candidate_source_sha256"), "extracted source digest was not reverified")
require(handoff.get("candidate_manifest_sha256") == binding.get("candidate_manifest_sha256"), "final handoff candidate manifest mismatch")
host = handoff.get("host") or {}
require(host.get("system") == "Darwin", "final handoff host is not Darwin")
require(str(host.get("machine") or "").lower() == "arm64", "final handoff host is not arm64")
require(host.get("is_ci") is False, "final handoff cannot come from CI")
require(host.get("physical_gate_eligible") is True, "final handoff host is not physical-gate eligible")
require(attestation.get("both_phases_passed") is True, "combined attestation does not have both phases passed")
require(attestation.get("release_authority") is False, "combined attestation unexpectedly has release authority")
require(attestation.get("publication_authority") in {None, False}, "combined attestation unexpectedly has publication authority")
require(attestation.get("production_ready") is False, "combined attestation unexpectedly reports production-ready")

old_sha = str(attestation.get("attestation_sha256") or "")
core = dict(attestation)
core.pop("generated_at", None)
core.pop("attestation_sha256", None)
require(len(old_sha) == 64 and digest(core) == old_sha, "pre-W97 combined attestation digest mismatch")

core["w97_integrity"] = {
    "schema": "binario.marketing.physical-uat-final-integrity.v1",
    "handoff_verification_sha256": file_sha(verify_path),
    "handoff_verification": handoff,
    "bundle_signature_verified": True,
    "codesign_requirement": ["--deep", "--strict"],
    "source_digest_reverified": True,
    "physical_host_reverified": True,
}
new_sha = digest(core)
sealed = {**core, "generated_at": attestation.get("generated_at"), "attestation_sha256": new_sha}
attestation_path.write_text(json.dumps(sealed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

summary = summary_path.read_text(encoding="utf-8")
if old_sha in summary:
    summary = summary.replace(old_sha, new_sha)
summary += (
    f"\n- W97 final handoff verification SHA-256: `{core['w97_integrity']['handoff_verification_sha256']}`\n"
    "- W97 final bundle signature reverified: **YES**\n"
    "- W97 extracted source digest reverified: **YES**\n"
)
summary_path.write_text(summary, encoding="utf-8")
print(json.dumps({
    "w97_final_integrity": True,
    "handoff_verification_sha256": core["w97_integrity"]["handoff_verification_sha256"],
    "attestation_sha256": new_sha,
    "release_authority": False,
    "publication_authority": False,
    "production_ready": False,
}, ensure_ascii=False, indent=2))
PY

printf '\nCOMBINED PHYSICAL UAT ATTESTATION CREATED AND W97-SEALED\n'
printf 'JSON: %s\n' "$ATTESTATION"
printf 'Summary: %s\n' "$SUMMARY"
printf 'Final handoff verification: %s\n' "$VERIFY_REPORT"
printf '\nThis does not create a tag, sign for distribution, notarize, or publish a release.\n'
/usr/bin/open "$OUT"
