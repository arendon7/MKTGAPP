#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <base-url> <embedded-python> <media-bin-dir> <tmp-dir>" >&2
  exit 2
fi
BASE="$1";PY="$2";MEDIA="$3";TMP="$4"
SPEECH_AIFF="$TMP/transcription-speech.aiff"

/usr/bin/say "Marketing content works better when the message is clear and the result is measured. This is a local transcription test for Binario Marketing." -o "$SPEECH_AIFF"
test -s "$SPEECH_AIFF"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data '{"name":"FULL MAC Transcription Smoke"}' "$BASE/api/projects" > "$TMP/transcription-project.json"
PROJECT_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["id"])' "$TMP/transcription-project.json")"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: audio/aiff' \
  --data-binary @"$SPEECH_AIFF" \
  "$BASE/api/projects/$PROJECT_ID/assets/upload?filename=local-speech.aiff&kind=audio" > "$TMP/transcription-asset.json"
ASSET_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["id"])' "$TMP/transcription-asset.json")"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data '{"language":"en"}' \
  "$BASE/api/projects/$PROJECT_ID/assets/$ASSET_ID/transcription" > "$TMP/transcription-start.json"

STATUS=""
for _ in $(seq 1 240); do
  /usr/bin/curl --fail --silent "$BASE/api/projects/$PROJECT_ID/assets/$ASSET_ID/transcription" > "$TMP/transcription-status.json"
  STATUS="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1],encoding="utf-8"))["status"])' "$TMP/transcription-status.json")"
  case "$STATUS" in
    PASS|FAIL|CANCELLED|INTERRUPTED) break ;;
  esac
  sleep 0.25
done
if [[ "$STATUS" != "PASS" ]]; then
  cat "$TMP/transcription-status.json" >&2 || true
  exit 1
fi

/usr/bin/curl --fail --silent "$BASE/api/projects/$PROJECT_ID/assets/$ASSET_ID/transcription/segments" > "$TMP/transcription-segments.json"
/usr/bin/curl --fail --silent "$BASE/api/projects/$PROJECT_ID/assets/$ASSET_ID/transcription/file" > "$TMP/transcription-file.json"
"$PY" -I -B - "$TMP/transcription-status.json" "$TMP/transcription-segments.json" "$TMP/transcription-file.json" <<'PY'
import json,sys
status=json.load(open(sys.argv[1],encoding='utf-8'))
segments=json.load(open(sys.argv[2],encoding='utf-8'))
payload=json.load(open(sys.argv[3],encoding='utf-8'))
assert status['engine']=='whisper.cpp',status
assert status['segments_count']>=1,status
assert float(status['duration'])>0,status
assert status.get('transcript_sha256'),status
assert status.get('model_sha256'),status
assert len(segments)>=1,segments
assert any(str(row.get('text','')).strip() for row in segments),segments
assert payload['asset_id']==status['asset_id'],payload
assert payload['source_sha256']==status['source_sha256'],payload
assert len(payload['segments'])==len(segments),payload
print('SMOKE PASS: local whisper.cpp transcription + managed transcript artifact')
PY

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data '{"target_count":1,"min_duration":1,"max_duration":30}' \
  "$BASE/api/projects/$PROJECT_ID/assets/$ASSET_ID/transcription/clips" > "$TMP/transcription-clips.json"
"$PY" -I -B - "$TMP/transcription-clips.json" <<'PY'
import json,sys
clips=json.load(open(sys.argv[1],encoding='utf-8'))
assert len(clips)>=1,clips
row=clips[0]
assert float(row['end'])>float(row['start'])>=0,row
assert str(row.get('text','')).strip(),row
print('SMOKE PASS: automatic transcript-driven Clipper')
PY

echo 'SMOKE PASS: offline transcription -> transcript -> automatic Clipper'
