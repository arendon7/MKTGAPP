#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

python -m unittest tests.test_post_w99_operator_session_progress
python -m py_compile src/binario_marketing/service_post_w99_operator_session_progress_app.py
node --check web/operator-session-progress.js

echo 'Post-W99 Operator Session Progress audit PASS'
