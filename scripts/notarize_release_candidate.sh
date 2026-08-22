#!/bin/bash
set -euo pipefail

APP="${1:-}"
OUT="${2:-}"
fail(){ printf 'RELEASE NOTARIZATION BLOCKED: %s\n' "$1" >&2; exit 4; }

[[ "$(uname -s)" == "Darwin" ]] || fail "notarization must run on macOS"
[[ -n "$APP" && -d "$APP" ]] || fail "app bundle missing"
[[ -n "$OUT" ]] || fail "evidence output path is required"
[[ -n "${APPLE_NOTARY_KEY_PATH:-}" && -f "${APPLE_NOTARY_KEY_PATH:-}" ]] || fail "APPLE_NOTARY_KEY_PATH missing"
[[ -n "${APPLE_NOTARY_KEY_ID:-}" ]] || fail "APPLE_NOTARY_KEY_ID missing"
[[ -n "${APPLE_NOTARY_ISSUER_ID:-}" ]] || fail "APPLE_NOTARY_ISSUER_ID missing"

IDENTITY="${BINARIO_CODESIGN_IDENTITY:-}"
[[ "$IDENTITY" == Developer\ ID\ Application:* ]] || fail "Developer ID Application identity is required"

/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"
SIGN_INFO="$(/usr/bin/codesign -dv --verbose=4 "$APP" 2>&1)"
printf '%s\n' "$SIGN_INFO" | /usr/bin/grep -F "Authority=$IDENTITY" >/dev/null || fail "app is not signed by expected Developer ID identity"

TMP="$(mktemp -d)"
cleanup(){ rm -rf "$TMP"; }
trap cleanup EXIT
ZIP="$TMP/notary-upload.zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "$APP" "$ZIP"

NOTARY_JSON="$TMP/notary.json"
/usr/bin/xcrun notarytool submit "$ZIP" \
  --key "$APPLE_NOTARY_KEY_PATH" \
  --key-id "$APPLE_NOTARY_KEY_ID" \
  --issuer "$APPLE_NOTARY_ISSUER_ID" \
  --wait \
  --output-format json > "$NOTARY_JSON"

python3 - "$NOTARY_JSON" <<'PY'
import json,sys
row=json.load(open(sys.argv[1],encoding='utf-8'))
status=str(row.get('status') or '').lower()
if status!='accepted':
    raise SystemExit(f"notary submission was not accepted: {row}")
if not row.get('id'):
    raise SystemExit('notary submission id missing')
PY

/usr/bin/xcrun stapler staple "$APP"
/usr/bin/xcrun stapler validate "$APP"
/usr/sbin/spctl --assess --type execute --verbose=4 "$APP"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$APP"

mkdir -p "$(dirname "$OUT")"
python3 - "$APP" "$NOTARY_JSON" "$OUT" "$IDENTITY" <<'PY'
import hashlib,json,subprocess,sys
from pathlib import Path
app=Path(sys.argv[1]).resolve(); notary=json.load(open(sys.argv[2],encoding='utf-8')); out=Path(sys.argv[3]); identity=sys.argv[4]
resources=app/'Contents/Resources'
provenance=json.load(open(resources/'BUILD_PROVENANCE.json',encoding='utf-8'))
candidate=resources/'PHYSICAL_UAT_CANDIDATE.json'

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

row={
  'schema':'binario.marketing.distribution-trust.v1',
  'git_sha':provenance.get('git_sha'),
  'architecture':provenance.get('architecture'),
  'product_version':provenance.get('product_version'),
  'runtime_wave':76,
  'signing_mode':'developer_id',
  'developer_id_identity':identity,
  'notarized':True,
  'notary_submission_id':notary.get('id'),
  'notary_status':notary.get('status'),
  'stapler_validated':True,
  'gatekeeper_assessed':True,
  'candidate_manifest_sha256':sha(candidate) if candidate.is_file() else None,
  'release_authority':False,
}
raw=json.dumps(row,sort_keys=True,separators=(',',':')).encode(); row['evidence_sha256']=hashlib.sha256(raw).hexdigest()
out.write_text(json.dumps(row,indent=2,sort_keys=True)+'\n',encoding='utf-8')
print(json.dumps({'git_sha':row['git_sha'],'architecture':row['architecture'],'notarized':True,'notary_submission_id':row['notary_submission_id'],'evidence':str(out)},sort_keys=True))
PY
