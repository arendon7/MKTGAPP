#!/bin/bash
set -euo pipefail

APP="${1:-}"
ARCH="${2:-}"
ROOT="${3:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "missing app bundle" >&2; exit 2; }
[[ "$ARCH" == "arm64" || "$ARCH" == "x86_64" ]] || { echo "invalid architecture" >&2; exit 2; }
[[ -n "$ROOT" && -d "$ROOT" ]] || { echo "missing repository root" >&2; exit 2; }

CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RES="$CONTENTS/Resources"
AGENTS="$CONTENTS/Library/LaunchAgents"
SERVICE_HELPER="$MACOS/binario-background-service"
AGENT="$MACOS/binario-background-agent"
PLIST="$AGENTS/com.sistemabinario.marketing.background.plist"
mkdir -p "$AGENTS"

[[ -f "$ROOT/native/background_service_helper.swift" ]] || { echo "background service helper source missing" >&2; exit 3; }
[[ -f "$ROOT/native/background_agent_launcher.c" ]] || { echo "background agent launcher source missing" >&2; exit 3; }

/usr/bin/xcrun --sdk macosx swiftc -O -target "$ARCH-apple-macos13.0" \
  "$ROOT/native/background_service_helper.swift" -framework Foundation -framework ServiceManagement -o "$SERVICE_HELPER"
/usr/bin/xcrun --sdk macosx clang -O2 -Wall -Wextra -target "$ARCH-apple-macos13.0" \
  "$ROOT/native/background_agent_launcher.c" -o "$AGENT"
chmod 755 "$SERVICE_HELPER" "$AGENT"

for binary in "$SERVICE_HELPER" "$AGENT"; do
  /usr/bin/file "$binary" | /usr/bin/grep -q 'Mach-O' || { echo "background executable is not Mach-O: $binary" >&2; exit 3; }
  ARCHS="$(/usr/bin/lipo -archs "$binary")"
  [[ " $ARCHS " == *" $ARCH "* ]] || { echo "background executable architecture mismatch: $ARCHS" >&2; exit 3; }
done

cat > "$RES/background_agent.py" <<'PY'
from __future__ import annotations
import sys
from pathlib import Path
resources = Path(__file__).resolve().parent
sys.path.insert(0, str(resources / "source" / "src"))
from binario_marketing.background_social_agent import main
raise SystemExit(main())
PY

cat > "$PLIST" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.sistemabinario.marketing.background</string>
<key>BundleProgram</key><string>Contents/MacOS/binario-background-agent</string>
<key>RunAtLoad</key><true/>
<key>StartInterval</key><integer>60</integer>
</dict></plist>
PLIST
/usr/bin/plutil -lint "$PLIST" >/dev/null
printf 'BACKGROUND SCHEDULER BUNDLE PASS: %s (%s)\n' "$APP" "$ARCH"
