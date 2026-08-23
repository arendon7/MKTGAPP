#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${1:-$ROOT/release-evidence}"
mkdir -p "$OUT"

printf 'BINARIO Marketing IA release dry run\n'
printf 'Mode: DRY_RUN\n'
printf 'Publication: DISABLED\n'

python3 "$ROOT/scripts/verify_release_tag.py" --dry-run "$OUT"

cat > "$OUT/DRY_RUN_REPORT.md" <<EOF
# Release Dry Run

Status: VALIDATION_ONLY

No public release was created.
No GitHub Release was published.
No production tag was created.

The pipeline verified release prerequisites only.
EOF

printf '{"schema":"binario.marketing.release-dry-run.v1","mode":"dry-run","production_release":false,"publication":false,"status":"PASS"}\n' > "$OUT/FINAL_RELEASE_CHECKLIST.json"

echo "RELEASE DRY RUN PASS"
echo "Publication intentionally disabled"
