#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
LAUNCHER="$APP/Contents/MacOS/Binario Marketing IA"
PY="$RES/runtime/python/bin/python3"
[[ -x "$LAUNCHER" ]] || { echo "missing launcher" >&2; exit 3; }
[[ -x "$PY" ]] || { echo "missing embedded python" >&2; exit 3; }
[[ -f "$RES/source/web/index.html" ]] || { echo "missing web UI" >&2; exit 3; }
[[ -f "$RES/source/apps/editor-video/manifest.json" ]] || { echo "missing app manifests" >&2; exit 3; }
/usr/bin/plutil -lint "$APP/Contents/Info.plist" >/dev/null
/usr/bin/codesign --verify --deep --strict "$APP"
if /usr/bin/grep -Eq '(^|[;&|[:space:]])python3([[:space:]]|$)' "$LAUNCHER"; then echo "launcher contains host python invocation" >&2; exit 3; fi
"$PY" -I -B - "$RES/source/src" "$RES/source" <<'PY'
import json, sys
from pathlib import Path
src, root = map(Path, sys.argv[1:3])
sys.path.insert(0, str(src))
from binario_marketing.hub import discover_apps
from binario_marketing.service import AppRuntime
apps = discover_apps(root)
assert len(apps) == 12, len(apps)
runtime = AppRuntime.create(root, Path('/tmp') / 'binario-audit-data')
assert len(runtime.apps_payload()) == 12
print(json.dumps({'apps': len(apps), 'status': 'PASS'}))
PY
printf 'FULL MAC AUDIT PASS: %s\n' "$APP"
