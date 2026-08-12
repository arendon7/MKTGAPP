#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "usage: $0 <base-url> <embedded-python> <media-bin-dir> <tmp-dir>" >&2
  exit 2
fi

BASE="$1"
PY="$2"
MEDIA="$3"
TMP="$4"

SOURCE_SILENT="$TMP/sequence-silent.mp4"
SOURCE_AUDIO="$TMP/sequence-audio.mp4"

"$MEDIA/ffmpeg" -hide_banner -loglevel error \
  -f lavfi -i 'testsrc2=size=640x360:rate=24' \
  -t 0.8 -c:v mpeg4 -an -y "$SOURCE_SILENT"

"$MEDIA/ffmpeg" -hide_banner -loglevel error \
  -f lavfi -i 'testsrc2=size=640x360:rate=24' \
  -f lavfi -i 'sine=frequency=440:sample_rate=48000' \
  -t 0.8 -c:v mpeg4 -c:a aac -shortest -y "$SOURCE_AUDIO"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data '{"name":"FULL MAC Sequence Smoke"}' \
  "$BASE/api/projects" > "$TMP/sequence-project.json"
PROJECT_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "$TMP/sequence-project.json")"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: video/mp4' \
  --data-binary @"$SOURCE_SILENT" \
  "$BASE/api/projects/$PROJECT_ID/assets/upload?filename=sequence-silent.mp4&kind=video" > "$TMP/sequence-asset-1.json"
ASSET1_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "$TMP/sequence-asset-1.json")"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: video/mp4' \
  --data-binary @"$SOURCE_AUDIO" \
  "$BASE/api/projects/$PROJECT_ID/assets/upload?filename=sequence-audio.mp4&kind=video" > "$TMP/sequence-asset-2.json"
ASSET2_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "$TMP/sequence-asset-2.json")"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data "{\"action\":\"add_clip\",\"asset_id\":\"$ASSET1_ID\",\"start\":0,\"end\":0.35,\"track\":0}" \
  "$BASE/api/projects/$PROJECT_ID/editor/actions" > "$TMP/sequence-editor-1.json"
CLIP1_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["clips"][0]["id"])' "$TMP/sequence-editor-1.json")"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data "{\"action\":\"add_clip\",\"asset_id\":\"$ASSET2_ID\",\"start\":0,\"end\":0.35,\"track\":0}" \
  "$BASE/api/projects/$PROJECT_ID/editor/actions" > "$TMP/sequence-editor-2.json"
CLIP2_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["clips"][1]["id"])' "$TMP/sequence-editor-2.json")"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data "{\"action\":\"reorder\",\"clip_id\":\"$CLIP2_ID\",\"direction\":-1}" \
  "$BASE/api/projects/$PROJECT_ID/editor/actions" > "$TMP/sequence-reordered.json"

"$PY" -I -B - "$TMP/sequence-reordered.json" "$CLIP2_ID" "$CLIP1_ID" <<'PY'
import json, sys
row=json.load(open(sys.argv[1], encoding='utf-8'))
order=[clip['id'] for clip in row['clips'] if int(clip.get('track', 0)) == 0]
assert order == [sys.argv[2], sys.argv[3]], order
print('SMOKE PASS: Track 0 reorder')
PY

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data '{"action":"subtitle_add","id":"sequence-sub","start":0.05,"end":0.6,"text":"Sequence subtitle"}' \
  "$BASE/api/projects/$PROJECT_ID/editor/actions" > "$TMP/sequence-subtitle.json"

/usr/bin/curl --fail --silent -X POST -H 'Content-Type: application/json' \
  --data '{"track":0,"aspect":"16:9","label":"ci-sequence-master"}' \
  "$BASE/api/projects/$PROJECT_ID/renders/sequence" > "$TMP/sequence-render-start.json"
JOB_ID="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "$TMP/sequence-render-start.json")"

STATUS=""
for _ in $(seq 1 160); do
  /usr/bin/curl --fail --silent "$BASE/api/renders/$JOB_ID" > "$TMP/sequence-render.json"
  STATUS="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["status"])' "$TMP/sequence-render.json")"
  case "$STATUS" in
    PASS|FAIL|CANCELLED|INTERRUPTED) break ;;
  esac
  sleep 0.25
done

if [[ "$STATUS" != "PASS" ]]; then
  cat "$TMP/sequence-render.json" >&2 || true
  exit 1
fi

"$PY" -I -B - "$TMP/sequence-render.json" "$CLIP2_ID" "$CLIP1_ID" "$ASSET2_ID" "$ASSET1_ID" <<'PY'
import json, math, sys
row=json.load(open(sys.argv[1], encoding='utf-8'))
assert row['kind'] == 'sequence', row
assert row['clip_ids'] == [sys.argv[2], sys.argv[3]], row
assert math.isclose(float(row['end']), 0.7, abs_tol=0.02), row
sources=set(row.get('source_asset_ids') or [])
assert {sys.argv[4], sys.argv[5]}.issubset(sources), row
assert row.get('composition_sha256'), row
assert row.get('subtitle_relative_path'), row
print('SMOKE PASS: sequence evidence + ordered clip ids')
PY

/usr/bin/curl --fail --silent "$BASE/api/renders/$JOB_ID/file" > "$TMP/sequence-master.mp4"
/usr/bin/curl --fail --silent "$BASE/api/renders/$JOB_ID/subtitles" > "$TMP/sequence-master.srt"
/usr/bin/grep -q 'Sequence subtitle' "$TMP/sequence-master.srt"
test -s "$TMP/sequence-master.mp4"

JOB_SHA="$("$PY" -I -B -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["sha256"])' "$TMP/sequence-render.json")"
FILE_SHA="$(/usr/bin/shasum -a 256 "$TMP/sequence-master.mp4" | /usr/bin/awk '{print $1}')"
[[ "$JOB_SHA" == "$FILE_SHA" ]]

"$MEDIA/ffprobe" -v error -select_streams v:0 -show_entries stream=width,height -of csv=p=0 "$TMP/sequence-master.mp4" > "$TMP/sequence-dimensions.txt"
/usr/bin/grep -q '^1920,1080$' "$TMP/sequence-dimensions.txt"
"$MEDIA/ffprobe" -v error -select_streams a:0 -show_entries stream=codec_type -of csv=p=0 "$TMP/sequence-master.mp4" > "$TMP/sequence-audio.txt"
/usr/bin/grep -q '^audio$' "$TMP/sequence-audio.txt"

DURATION="$("$MEDIA/ffprobe" -v error -show_entries format=duration -of default=nw=1:nk=1 "$TMP/sequence-master.mp4")"
"$PY" -I -B - "$DURATION" <<'PY'
import math, sys
value=float(sys.argv[1])
assert math.isclose(value, 0.7, abs_tol=0.12), value
PY

echo "SMOKE PASS: native Track 0 sequence master + mixed source/silence audio + SRT + SHA256 ($FILE_SHA)"
