#!/bin/bash
set -euo pipefail
APP="${1:?usage: audit_wave71_candidate_certification_dossier.sh <app>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$APP/Contents/Resources/source"
LAUNCH="$APP/Contents/Resources/launch.py"
[[ -f "$SRC/src/binario_marketing/service_wave71_app.py" ]]
[[ -f "$SRC/web/candidate-certification-dossier.js" ]]
[[ -f "$LAUNCH" ]]
/usr/bin/grep -q 'binario.marketing.candidate-certification-dossier.v1' "$SRC/src/binario_marketing/service_wave71_app.py"
/usr/bin/grep -q 'dossier_is_release_authority' "$SRC/src/binario_marketing/service_wave71_app.py"
/usr/bin/grep -q 'release_state_mutation_performed' "$SRC/src/binario_marketing/service_wave71_app.py"
/usr/bin/grep -q 'service_wave71_app import serve' "$LAUNCH"
/usr/bin/grep -q 'candidate-certification-dossier.js' "$SRC/src/binario_marketing/service_wave71_app.py"
/usr/bin/grep -q 'Expediente del candidato físico' "$SRC/web/candidate-certification-dossier.js"
! /usr/bin/grep -q "method:'POST'" "$SRC/web/candidate-certification-dossier.js"
! /usr/bin/grep -q "method:'PATCH'" "$SRC/web/candidate-certification-dossier.js"
! /usr/bin/grep -q 'setInterval' "$SRC/web/candidate-certification-dossier.js"
! /usr/bin/grep -q 'RELEASE_READY = True' "$SRC/src/binario_marketing/service_wave71_app.py"
[[ "$(find "$ROOT/.github/workflows" -maxdepth 1 -name '*.yml' | wc -l | tr -d ' ')" == "3" ]]
echo 'WAVE 71 CANDIDATE CERTIFICATION DOSSIER AUDIT PASS'
