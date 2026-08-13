#!/bin/bash
set -euo pipefail

APP="${1:-}"
ARCH="${2:-}"
ROOT="${3:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/app arch repo-root" >&2; exit 2; }
[[ "$ARCH" == "arm64" || "$ARCH" == "x86_64" ]] || { echo "invalid architecture" >&2; exit 2; }
[[ -n "$ROOT" && -d "$ROOT" ]] || { echo "invalid repo root" >&2; exit 2; }

CONTENTS="$APP/Contents"
MACOS="$CONTENTS/MacOS"
RESOURCES="$CONTENTS/Resources"
LAUNCH_AGENTS="$CONTENTS/Library/LaunchAgents"
SERVICE_HELPER="$MACOS/binario-background-service"
AGENT="$MACOS/binario-background-agent"
PLIST="$LAUNCH_AGENTS/com.sistemabinario.marketing.background.plist"
mkdir -p "$LAUNCH_AGENTS"

SERVICE_SOURCE="$ROOT/native/background_service_helper.swift"
AGENT_SOURCE="$ROOT/native/background_agent_launcher.swift"
[[ -f "$SERVICE_SOURCE" ]] || { echo "background service helper source missing" >&2; exit 3; }
[[ -f "$AGENT_SOURCE" ]] || { echo "background agent launcher source missing" >&2; exit 3; }

/usr/bin/xcrun --sdk macosx swiftc -O -target "$ARCH-apple-macos13.0" \
  "$SERVICE_SOURCE" -framework Foundation -framework ServiceManagement -o "$SERVICE_HELPER"
[[ -x "$SERVICE_HELPER" ]] || { echo "background service helper build failed" >&2; exit 3; }
SERVICE_ARCHS="$(/usr/bin/lipo -archs "$SERVICE_HELPER")"
[[ " $SERVICE_ARCHS " == *" $ARCH "* ]] || { echo "background service helper architecture mismatch: $SERVICE_ARCHS" >&2; exit 3; }

/usr/bin/xcrun --sdk macosx swiftc -O -target "$ARCH-apple-macos13.0" \
  "$AGENT_SOURCE" -framework Foundation -o "$AGENT"
[[ -x "$AGENT" ]] || { echo "background agent launcher build failed" >&2; exit 3; }
AGENT_ARCHS="$(/usr/bin/lipo -archs "$AGENT")"
[[ " $AGENT_ARCHS " == *" $ARCH "* ]] || { echo "background agent launcher architecture mismatch: $AGENT_ARCHS" >&2; exit 3; }

cat > "$RESOURCES/background_agent.py" <<'PY'
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
printf 'WAVE 28 BACKGROUND BUNDLE PASS: %s\n' "$ARCH"
