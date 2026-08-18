#!/bin/bash
set -euo pipefail
APP="${1:-}"
[[ -n "$APP" && -d "$APP" ]] || { echo "usage: $0 /path/to/Binario Marketing IA.app" >&2; exit 2; }
RES="$APP/Contents/Resources"
UI="$RES/source/web/ai-copilot.js"
SERVICE="$RES/source/src/binario_marketing/service_wave51_app.py"
PROVIDER="$RES/source/src/binario_marketing/ai_provider.py"
CREDS="$RES/source/src/binario_marketing/ai_credentials.py"
STORE="$RES/source/src/binario_marketing/ai_store.py"
LOADER="$RES/source/web/audiences-wave39-loader.js"
[[ -f "$UI" && -f "$SERVICE" && -f "$PROVIDER" && -f "$CREDS" && -f "$STORE" && -f "$LOADER" ]] || { echo "Wave 51 audit: AI Copilot source missing" >&2; exit 3; }
/usr/bin/grep -q 'service_wave51_app import serve' "$RES/launch.py" || { echo "Wave 51 audit: Mac launch is not using Wave 51" >&2; exit 3; }
for text in 'AI COPILOT' 'Pensar mejor, no automatizar a ciegas' 'Guardar en Keychain' 'Generar con IA' 'Usar en Creative Studio'; do
  /usr/bin/grep -q "$text" "$UI" || { echo "Wave 51 audit: missing product contract: $text" >&2; exit 3; }
done
/usr/bin/grep -q "ai.src='/ai-copilot.js'" "$LOADER" || { echo "Wave 51 audit: loader missing" >&2; exit 3; }
/usr/bin/grep -q 'binario.marketing.ai-context.v1' "$SERVICE" || { echo "Wave 51 audit: sanitized context schema missing" >&2; exit 3; }
/usr/bin/grep -q 'contact_pii_included.*False' "$SERVICE" || { echo "Wave 51 audit: PII exclusion contract missing" >&2; exit 3; }
/usr/bin/grep -q 'provider_secrets_included.*False' "$SERVICE" || { echo "Wave 51 audit: secret exclusion contract missing" >&2; exit 3; }
/usr/bin/grep -q 'api.openai.com/v1/responses' "$PROVIDER" || { echo "Wave 51 audit: OpenAI adapter missing" >&2; exit 3; }
/usr/bin/grep -q 'api.anthropic.com/v1/messages' "$PROVIDER" || { echo "Wave 51 audit: Anthropic adapter missing" >&2; exit 3; }
/usr/bin/grep -q 'generateContent' "$PROVIDER" || { echo "Wave 51 audit: Gemini adapter missing" >&2; exit 3; }
/usr/bin/grep -q '127.0.0.1:11434/api/chat' "$PROVIDER" || { echo "Wave 51 audit: Ollama adapter missing" >&2; exit 3; }
/usr/bin/grep -q 'AI_SESSION_SCHEMA' "$STORE" || { echo "Wave 51 audit: session provenance store missing" >&2; exit 3; }
[[ -x "$APP/Contents/MacOS/binario-meta-keychain" ]] || { echo "Wave 51 audit: native Keychain helper missing" >&2; exit 3; }
printf 'WAVE 51 AI COPILOT AUDIT PASS\n'
