#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
fail(){ printf 'PHYSICAL UAT START BLOCKED: %s\n' "$1" >&2; exit 4; }

[[ "$(uname -s)" == "Darwin" ]] || fail "this handoff must run on macOS"
[[ "$(uname -m)" == "arm64" ]] || fail "physical UAT requires an Apple Silicon arm64 Mac"
[[ "${GITHUB_ACTIONS:-}" != "true" && "${CI:-}" != "true" ]] || fail "physical UAT cannot run in CI"

shopt -s nullglob
ZIPS=(Binario-Marketing-IA-PHYSICAL-UAT-arm64-*.zip)
[[ ${#ZIPS[@]} -eq 1 ]] || fail "expected exactly one PHYSICAL-UAT arm64 ZIP in this folder"
ZIP="${ZIPS[0]}"
CHECKSUM="$ZIP.sha256"
[[ -f "$CHECKSUM" ]] || fail "checksum sidecar missing: $CHECKSUM"
/usr/bin/shasum -a 256 -c "$CHECKSUM"

WORK="$ROOT/PHYSICAL_UAT_WORK"
APP="$WORK/Binario Marketing IA.app"
rm -rf "$WORK"
mkdir -p "$WORK"
/usr/bin/ditto -x -k "$ZIP" "$WORK"
[[ -d "$APP" ]] || fail "extracted app missing: $APP"
/usr/bin/codesign --verify --deep --strict "$APP"

PY="$APP/Contents/Resources/runtime/python/bin/python3"
COLLECT="$APP/Contents/Resources/release-tools/collect_release_uat.py"
VERIFY="$ROOT/PHYSICAL_UAT_HANDOFF_VERIFY.py"
[[ -x "$PY" ]] || fail "embedded Python runtime missing"
[[ -f "$COLLECT" ]] || fail "embedded release UAT collector missing"
[[ -f "$VERIFY" ]] || fail "handoff verifier missing"

"$PY" -I -B "$VERIFY" \
  --delivery-dir "$ROOT" \
  --app "$APP" \
  --require-physical-host > "$ROOT/PHYSICAL_UAT_HANDOFF_VERIFICATION.json"
cat "$ROOT/PHYSICAL_UAT_HANDOFF_VERIFICATION.json"

EVIDENCE_DIR="$ROOT/PHYSICAL_UAT_EVIDENCE"
EVIDENCE_JSON="$EVIDENCE_DIR/release-uat-evidence.json"
mkdir -p "$EVIDENCE_DIR"
if [[ ! -f "$EVIDENCE_JSON" ]]; then
  "$PY" -I -B "$COLLECT" --app "$APP" --output "$EVIDENCE_DIR"
else
  "$PY" -I -B - "$EVIDENCE_JSON" "$ROOT/FULL_MAC_DELIVERY.json" <<'PY'
import json,sys
from pathlib import Path
evidence=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
delivery=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
checks={
    'schema': evidence.get('schema') == 'binario.marketing.release-uat-evidence.v1',
    'git_sha': evidence.get('git_sha') == delivery.get('git_sha'),
    'architecture': evidence.get('architecture') == 'arm64',
    'runtime_wave': evidence.get('runtime_wave') == 76,
    'source_contract_wave': evidence.get('source_contract_wave') == delivery.get('source_contract_wave') == 94,
    'source_digest': evidence.get('candidate_source_sha256') == delivery.get('candidate_source_sha256'),
    'manifest_digest': evidence.get('candidate_manifest_sha256') == delivery.get('candidate_manifest_sha256'),
    'source_release_state': evidence.get('source_release_state') == delivery.get('source_release_state'),
    'source_release_tag': evidence.get('source_release_tag') == delivery.get('source_release_tag'),
}
failed=[name for name,ok in checks.items() if not ok]
if failed:
    raise SystemExit('existing UAT evidence belongs to another candidate/source state: '+', '.join(failed))
print('Existing release UAT evidence is bound to this exact W94 candidate and source release state; preserving recorded manual gates.')
PY
fi

/usr/bin/open "$APP"

cat <<'TXT'

PHYSICAL UAT HANDOFF READY

FASE A · UAT física dentro de la app
1. Abra/seleccione una empresa controlada.
2. Entre al panel UAT física guiada.
3. Inicie una sesión UAT con operador y notas.
4. Ejecute y registre los 5 escenarios obligatorios:
   - company-switch
   - inbox-to-crm
   - pipeline-followup
   - campaign-execution
   - results-decision
5. optional-ai es opcional y no bloquea el core.
6. Finalice la sesión. Debe quedar PASSED + physical_uat_complete=true en este Mac físico.
7. Confirme en Release Evidence que la sesión es accepted_for_current_build=true.

FASE B · UAT operativa de release
- Use RECORD_RELEASE_UAT.command para registrar los 12 gates manuales.
- Cada gate exige PASS/FAIL y una nota concreta.
- No marque PASS por inferencia: ejecute la acción observada.

WAVE 94 · SOURCE STATE
- LOCKED_SOURCE puede probar el producto pero nunca autoriza un release futuro.
- PREPARED_RELEASE congela versión/tag antes de UAT; sigue sin ser autoridad ni build de distribución.
- La evidencia se preserva únicamente si wave 94, SHA, fuente, manifiesto, source state y prepared tag coinciden exactamente.

NINGUNA de estas acciones crea tags, firma con Developer ID, notariza o publica la app.
TXT

printf '\nEvidence folder: %s\n' "$EVIDENCE_DIR"
printf 'Operator guide: %s\n' "$ROOT/PHYSICAL_UAT_OPERATOR.md"
printf 'Candidate app: %s\n' "$APP"
