from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, text: str) -> None:
    (ROOT / path).write_text(text, encoding="utf-8")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"reconciliation anchor missing: {label}")
    return text.replace(old, new, 1)


# 1) Resolve embedded whisper runtime before any host PATH fallback.
path = "src/binario_marketing/video/transcription.py"
text = read(path)
if "import sys\n" not in text:
    text = text.replace("import shutil\n", "import shutil\nimport sys\n", 1)
old = '''def resolve_whisper_cli(explicit:str|None=None) -> str:\n    candidate=explicit or os.environ.get('BINARIO_WHISPER_CLI') or shutil.which('whisper-cli')\n    if not candidate:raise FileNotFoundError('whisper.cpp CLI runtime is unavailable')\n    return candidate\n\n\ndef resolve_whisper_model(explicit:str|None=None) -> str:\n    candidate=explicit or os.environ.get('BINARIO_WHISPER_MODEL')\n    if not candidate:raise FileNotFoundError('whisper.cpp model is unavailable')\n    path=Path(candidate)\n    if not path.is_file():raise FileNotFoundError(path)\n    return str(path)\n'''
new = '''def _embedded_runtime_file(relative:str) -> Path | None:\n    executable=Path(sys.executable).resolve()\n    if len(executable.parents)>=3:\n        runtime=executable.parents[2]\n        if runtime.name=='runtime':\n            candidate=runtime/relative\n            if candidate.is_file():return candidate\n    return None\n\n\ndef resolve_whisper_cli(explicit:str|None=None) -> str:\n    candidate=explicit or os.environ.get('BINARIO_WHISPER_CLI')\n    if not candidate:\n        embedded=_embedded_runtime_file('transcription/bin/whisper-cli')\n        candidate=str(embedded) if embedded is not None else shutil.which('whisper-cli')\n    if not candidate:raise FileNotFoundError('whisper.cpp CLI runtime is unavailable')\n    return candidate\n\n\ndef resolve_whisper_model(explicit:str|None=None) -> str:\n    candidate=explicit or os.environ.get('BINARIO_WHISPER_MODEL')\n    if not candidate:\n        embedded=_embedded_runtime_file('transcription/models/ggml-tiny.bin')\n        candidate=str(embedded) if embedded is not None else None\n    if not candidate:raise FileNotFoundError('whisper.cpp model is unavailable')\n    path=Path(candidate)\n    if not path.is_file():raise FileNotFoundError(path)\n    return str(path)\n'''
if "def _embedded_runtime_file(" not in text:
    text = replace_once(text, old, new, "whisper resolver")
write(path, text)

# 2) Make transcript model evidence and lifecycle use the same resolved runtime.
path = "src/binario_marketing/transcription_manager.py"
text = read(path)
text = text.replace(
    "from .video.transcription import SpeechSegment,extract_audio_command,load_whisper_output,transcript_sha256,whisper_command",
    "from .video.transcription import SpeechSegment,extract_audio_command,load_whisper_output,resolve_whisper_model,transcript_sha256,whisper_command",
)
old = '''    def _model_sha(self)->str|None:\n        if self._model_sha_cache:return self._model_sha_cache\n        candidate=self.model or os.environ.get('BINARIO_WHISPER_MODEL')\n        if candidate and Path(candidate).is_file():self._model_sha_cache=_sha256_file(Path(candidate));return self._model_sha_cache\n        return None\n'''
new = '''    def _model_sha(self)->str|None:\n        if self._model_sha_cache:return self._model_sha_cache\n        try:\n            candidate=resolve_whisper_model(self.model)\n        except FileNotFoundError:\n            return None\n        self._model_sha_cache=_sha256_file(Path(candidate))\n        return self._model_sha_cache\n'''
if old in text:
    text = text.replace(old, new, 1)
anchor = '''    def list(self,project_id:str|None=None)->list[TranscriptRecord]:\n        with self._lock:rows=self._load()\n        return [row for row in rows if project_id is None or row.project_id==project_id]\n'''
helpers = '''\n    def active_for_asset(self,project_id:str,asset_id:str)->bool:\n        row=self.get(project_id,asset_id)\n        return row is not None and row.status in TRANSCRIPTION_ACTIVE\n\n    def _remove_record(self,project_id:str,asset_id:str)->None:\n        with self._lock:self._save([row for row in self._load() if not (row.project_id==project_id and row.asset_id==asset_id)])\n\n    def invalidate(self,project_id:str,asset_id:str)->None:\n        row=self.get(project_id,asset_id)\n        if row is None:return\n        if row.status in TRANSCRIPTION_ACTIVE:raise ValueError('asset has an active transcription job')\n        if row.transcript_relative_path:\n            project_root=self.projects.path_for(project_id).resolve();path=(project_root/row.transcript_relative_path).resolve();root=self._transcripts_dir(project_id)\n            if root not in path.parents:raise ValueError('transcript path escaped managed transcripts root')\n            path.unlink(missing_ok=True)\n        self._remove_record(project_id,asset_id)\n        self.workspace.registries.timeline.append('transcription.invalidated',{'project_id':project_id,'asset_id':asset_id})\n'''
if "def active_for_asset(" not in text:
    text = replace_once(text, anchor, anchor + helpers, "transcription lifecycle")
write(path, text)

# 3) Wire automatic transcription and narrative clipper into the actual HTTP runtime.
path = "src/binario_marketing/service.py"
text = read(path)
if "from .clipper_service import select_clips_payload" not in text:
    text = text.replace("from .config import default_paths\n", "from .config import default_paths\nfrom .clipper_service import select_clips_payload\n", 1)
if "from .transcription_manager import TranscriptionManager" not in text:
    text = text.replace(
        "from .sequence_service import start_sequence_render\n",
        "from .sequence_service import start_sequence_render\nfrom .transcription_manager import TranscriptionManager\nfrom .transcription_service import select_transcript_clips\n",
        1,
    )
if "    transcriptions: TranscriptionManager\n" not in text:
    text = replace_once(
        text,
        "    proxies: ProxyManager\n    renders: RenderQueue\n",
        "    proxies: ProxyManager\n    transcriptions: TranscriptionManager\n    renders: RenderQueue\n",
        "AppRuntime field",
    )
old = '''        proxies = ProxyManager(user_root / "State" / "proxies", projects, workspace)\n        renders = RenderQueue(user_root / "State" / "renders", projects, workspace)\n        return cls(root, user_root, projects, workspace, editors, proxies, renders)\n'''
new = '''        proxies = ProxyManager(user_root / "State" / "proxies", projects, workspace)\n        transcriptions = TranscriptionManager(user_root / "State" / "transcriptions", projects, workspace)\n        renders = RenderQueue(user_root / "State" / "renders", projects, workspace)\n        return cls(root, user_root, projects, workspace, editors, proxies, transcriptions, renders)\n'''
if "transcriptions = TranscriptionManager(" not in text:
    text = replace_once(text, old, new, "AppRuntime create")
old = '''        proxies = {}\n        for asset in assets:\n            record = self.proxies.get(project_id, asset.id)\n            if record is not None:\n                proxies[asset.id] = asdict(record)\n        return {\n'''
new = '''        proxies = {}\n        transcriptions = {}\n        for asset in assets:\n            record = self.proxies.get(project_id, asset.id)\n            if record is not None:\n                proxies[asset.id] = asdict(record)\n            transcript = self.transcriptions.get(project_id, asset.id)\n            if transcript is not None:\n                transcriptions[asset.id] = asdict(transcript)\n        return {\n'''
if "transcriptions = {}" not in text:
    text = replace_once(text, old, new, "project detail transcription map")
if '"transcriptions": transcriptions' not in text:
    text = replace_once(
        text,
        '            "proxies": proxies,\n            "editor": self.editors.state(project_id),\n',
        '            "proxies": proxies,\n            "transcriptions": transcriptions,\n            "editor": self.editors.state(project_id),\n',
        "project detail payload",
    )
old = '''        if self.proxies.active_for_asset(project_id, asset_id):\n            raise ValueError("asset is referenced by an active preview proxy job")\n        for row in self.renders.list(project_id):\n'''
new = '''        if self.proxies.active_for_asset(project_id, asset_id):\n            raise ValueError("asset is referenced by an active preview proxy job")\n        if self.transcriptions.active_for_asset(project_id, asset_id):\n            raise ValueError("asset is referenced by an active transcription job")\n        for row in self.renders.list(project_id):\n'''
if "active transcription job" not in text:
    text = replace_once(text, old, new, "asset deletion active transcription")
if "self.transcriptions.invalidate(project_id, asset_id)" not in text:
    text = replace_once(
        text,
        "        self.proxies.invalidate(project_id, asset_id)\n        if not self.projects.remove_asset(project_id, asset_id):\n",
        "        self.proxies.invalidate(project_id, asset_id)\n        self.transcriptions.invalidate(project_id, asset_id)\n        if not self.projects.remove_asset(project_id, asset_id):\n",
        "asset transcription invalidation",
    )
if "def _transcript_file(" not in text:
    helper = '''    def _transcript_file(self, project_id: str, asset_id: str) -> None:\n        row = self.server.runtime.transcriptions.get(project_id, asset_id)\n        if row is None or row.status != "PASS":\n            raise ValueError("transcript is not available until transcription passes")\n        path = self.server.runtime.transcriptions.transcript_path(project_id, asset_id)\n        self._stream_file(path, "application/json; charset=utf-8", attachment=path.name)\n\n'''
    text = replace_once(text, "    def _render_file(self, job_id: str) -> None:\n", helper + "    def _render_file(self, job_id: str) -> None:\n", "transcript streamer")
if '"/transcription.js"' not in text:
    text = replace_once(
        text,
        '"/visual-timeline.js", "/styles.css"',
        '"/visual-timeline.js", "/transcription.js", "/clipper-modes.js", "/styles.css"',
        "static transcription bundles",
    )
elif '"/clipper-modes.js"' not in text:
    text = replace_once(text, '"/transcription.js", "/styles.css"', '"/transcription.js", "/clipper-modes.js", "/styles.css"', "static clipper bundle")
get_anchor = '''            elif len(parts) == 7 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5:] == ["proxy", "file"]:\n                self._proxy_file(parts[2], parts[4])\n'''
get_routes = '''            elif len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5] == "transcription":\n                row = self.server.runtime.transcriptions.get(parts[2], parts[4])\n                self._json(asdict(row) if row is not None else {"project_id": parts[2], "asset_id": parts[4], "status": "NONE"})\n            elif len(parts) == 7 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5:] == ["transcription", "segments"]:\n                self._json(self.server.runtime.transcriptions.segments(parts[2], parts[4]))\n            elif len(parts) == 7 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5:] == ["transcription", "file"]:\n                self._transcript_file(parts[2], parts[4])\n'''
if '["transcription", "segments"]' not in text:
    text = replace_once(text, get_anchor, get_anchor + get_routes, "GET transcription routes")
post_anchor = '''                elif len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5] == "proxy":\n                    self._json(self.server.runtime.ensure_proxy(parts[2], parts[4]), HTTPStatus.ACCEPTED)\n'''
post_routes = '''                elif len(parts) == 6 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5] == "transcription":\n                    self._json(asdict(self.server.runtime.transcriptions.ensure(parts[2], parts[4], str(payload.get("language", "auto")), bool(payload.get("force", False)))), HTTPStatus.ACCEPTED)\n                elif len(parts) == 7 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5:] == ["transcription", "cancel"]:\n                    self._json(asdict(self.server.runtime.transcriptions.cancel(parts[2], parts[4])))\n                elif len(parts) == 7 and parts[:2] == ["api", "projects"] and parts[3] == "assets" and parts[5:] == ["transcription", "clips"]:\n                    self._json(select_transcript_clips(self.server.runtime, parts[2], parts[4], payload))\n'''
if '["transcription", "clips"]' not in text:
    text = replace_once(text, post_anchor, post_anchor + post_routes, "POST transcription routes")
old = '''                    segments = [TranscriptSegment(float(row["start"]), float(row["end"]), str(row["text"])) for row in payload.get("segments", [])]\n                    self._json([asdict(item) for item in select_clips(segments, int(payload.get("target_count", 3)), float(payload.get("min_duration", 15)), float(payload.get("max_duration", 75)))])\n'''
new = '''                    segments = [TranscriptSegment(float(row["start"]), float(row["end"]), str(row["text"])) for row in payload.get("segments", [])]\n                    self._json(select_clips_payload(segments, payload))\n'''
if "self._json(select_clips_payload(segments, payload))" not in text:
    text = replace_once(text, old, new, "manual narrative clipper API")
if "runtime.transcriptions.shutdown()" not in text:
    text = replace_once(
        text,
        "        runtime.proxies.shutdown()\n        runtime.renders.shutdown()\n",
        "        runtime.proxies.shutdown()\n        runtime.transcriptions.shutdown()\n        runtime.renders.shutdown()\n",
        "transcription shutdown",
    )
write(path, text)

# 4) Make transcript-driven Clipper use the same natural/objective selector.
write(
    "src/binario_marketing/transcription_service.py",
    """from __future__ import annotations\n\nfrom .clipper_service import select_clips_payload\n\n\ndef select_transcript_clips(runtime,project_id:str,asset_id:str,payload:dict)->list[dict]:\n    rows=runtime.transcriptions.segments(project_id,asset_id)\n    return select_clips_payload(rows,payload)\n""",
)

# 5) Browser: load actual modules and pass narrative mode payload through both Clipper paths.
path = "web/index.html"
text = read(path)
if '<script src="/transcription.js" defer></script>' not in text:
    text = replace_once(
        text,
        '  <script src="/visual-timeline.js" defer></script>\n',
        '  <script src="/visual-timeline.js" defer></script>\n  <script src="/transcription.js" defer></script>\n  <script src="/clipper-modes.js" defer></script>\n',
        "browser transcription bundle",
    )
elif '<script src="/clipper-modes.js" defer></script>' not in text:
    text = text.replace('  <script src="/transcription.js" defer></script>\n', '  <script src="/transcription.js" defer></script>\n  <script src="/clipper-modes.js" defer></script>\n', 1)
write(path, text)

path = "web/app.js"
text = read(path)
old = "body:{segments,target_count:Number($('#clipper-count').value),min_duration:Number($('#clipper-min').value),max_duration:Number($('#clipper-max').value)}"
new = "body:{segments,target_count:Number($('#clipper-count').value),min_duration:Number($('#clipper-min').value),max_duration:Number($('#clipper-max').value),...(globalThis.clipperModePayload?clipperModePayload():{})}"
if "globalThis.clipperModePayload" not in text:
    text = replace_once(text, old, new, "manual browser clipper payload")
oldrow = "item.append(el('strong','',`${clip.start.toFixed(1)}–${clip.end.toFixed(1)}s · score ${clip.score}`),el('p','',clip.text));"
newrow = oldrow + "if(clip.tone)item.append(el('span','narrative-meta',`${clip.tone} · ${(clip.reasons||[]).join(' · ')}`));"
if "narrative-meta" not in text and oldrow in text:
    text = text.replace(oldrow, newrow, 1)
write(path, text)

path = "web/transcription.js"
text = read(path)
old = "body:{target_count:Number($('#clipper-count').value),min_duration:Number($('#clipper-min').value),max_duration:Number($('#clipper-max').value)}"
new = "body:{target_count:Number($('#clipper-count').value),min_duration:Number($('#clipper-min').value),max_duration:Number($('#clipper-max').value),...(globalThis.clipperModePayload?clipperModePayload():{})}"
if "globalThis.clipperModePayload" not in text:
    text = replace_once(text, old, new, "transcript browser clipper payload")
if "narrative-meta" not in text and oldrow in text:
    text = text.replace(oldrow, newrow, 1)
write(path, text)

# 6) Bundle pinned Whisper before final app codesign, not after it.
path = "scripts/build_full_mac_app.sh"
text = read(path)
if 'source "$ROOT/scripts/full_mac_transcription_runtime.env"' not in text:
    text = text.replace('source "$ROOT/scripts/full_mac_media_runtime.env"\n', 'source "$ROOT/scripts/full_mac_media_runtime.env"\n# shellcheck disable=SC1091\nsource "$ROOT/scripts/full_mac_transcription_runtime.env"\n', 1)
if 'TRANSCRIPTION_RUNTIME="$RESOURCES/runtime/transcription"' not in text:
    text = text.replace('MEDIA_RUNTIME="$RESOURCES/runtime/media"\n', 'MEDIA_RUNTIME="$RESOURCES/runtime/media"\nTRANSCRIPTION_RUNTIME="$RESOURCES/runtime/transcription"\n', 1)
if "build_embedded_whisper.sh" not in text:
    text = replace_once(
        text,
        '"$ROOT/scripts/build_embedded_ffmpeg.sh" --target "$MEDIA_RUNTIME" --arch "$ARCH"\n',
        '"$ROOT/scripts/build_embedded_ffmpeg.sh" --target "$MEDIA_RUNTIME" --arch "$ARCH"\n"$ROOT/scripts/build_embedded_whisper.sh" --arch "$ARCH" --output "$TRANSCRIPTION_RUNTIME"\n"$ROOT/scripts/audit_embedded_whisper.sh" "$APP" "$ARCH"\n',
        "Whisper app build",
    )
if '"embedded_whisper"' not in text:
    text = replace_once(
        text,
        '  "ffmpeg_source_commit": "$FULL_MAC_FFMPEG_COMMIT_SHA"\n',
        '  "ffmpeg_source_commit": "$FULL_MAC_FFMPEG_COMMIT_SHA",\n  "embedded_whisper": "$WHISPER_TAG",\n  "whisper_source_commit": "$WHISPER_COMMIT",\n  "whisper_model": "$WHISPER_MODEL_NAME",\n  "whisper_model_sha256": "$WHISPER_MODEL_SHA256"\n',
        "Whisper provenance",
    )
if 'BINARIO_WHISPER_CLI' not in text:
    text = replace_once(
        text,
        'os.environ.setdefault("BINARIO_FFPROBE", str(resources / "runtime" / "media" / "bin" / "ffprobe"))\n',
        'os.environ.setdefault("BINARIO_FFPROBE", str(resources / "runtime" / "media" / "bin" / "ffprobe"))\nos.environ.setdefault("BINARIO_WHISPER_CLI", str(resources / "runtime" / "transcription" / "bin" / "whisper-cli"))\nos.environ.setdefault("BINARIO_WHISPER_MODEL", str(resources / "runtime" / "transcription" / "models" / "ggml-tiny.bin"))\n',
        "launch Whisper env",
    )
if 'TRANSCRIPTION="$RESOURCES/runtime/transcription"' not in text:
    text = text.replace('MEDIA_BIN="$RESOURCES/runtime/media/bin"\n', 'MEDIA_BIN="$RESOURCES/runtime/media/bin"\nTRANSCRIPTION="$RESOURCES/runtime/transcription"\n', 1)
    text = text.replace('[[ -x "$MEDIA_BIN/ffmpeg" && -x "$MEDIA_BIN/ffprobe" ]] || { echo "BINARIO Marketing media runtime missing" >&2; exit 5; }\n', '[[ -x "$MEDIA_BIN/ffmpeg" && -x "$MEDIA_BIN/ffprobe" ]] || { echo "BINARIO Marketing media runtime missing" >&2; exit 5; }\n[[ -x "$TRANSCRIPTION/bin/whisper-cli" && -f "$TRANSCRIPTION/models/ggml-tiny.bin" ]] || { echo "BINARIO Marketing transcription runtime missing" >&2; exit 5; }\n', 1)
    text = text.replace('export PATH="$MEDIA_BIN:$RESOURCES/runtime/python/bin:/usr/bin:/bin"\n', 'export PATH="$TRANSCRIPTION/bin:$MEDIA_BIN:$RESOURCES/runtime/python/bin:/usr/bin:/bin"\n', 1)
    text = text.replace('export BINARIO_FFPROBE="$MEDIA_BIN/ffprobe"\n', 'export BINARIO_FFPROBE="$MEDIA_BIN/ffprobe"\nexport BINARIO_WHISPER_CLI="$TRANSCRIPTION/bin/whisper-cli"\nexport BINARIO_WHISPER_MODEL="$TRANSCRIPTION/models/ggml-tiny.bin"\n', 1)
write(path, text)

# Avoid pipefail/early-closing pipeline in Whisper binary discovery.
path = "scripts/build_embedded_whisper.sh"
text = read(path).replace('BUILT="$(find "$BUILD" -type f -name whisper-cli -perm -111 | head -n 1)"', 'BUILT="$(find "$BUILD" -type f -name whisper-cli -perm -111 -print -quit)"')
write(path, text)

# 7) FULL MAC must really build/audit/run the new runtime on both architectures.
path = ".github/workflows/full-mac-app.yml"
text = read(path)
if "Cache verified Whisper runtime" not in text:
    marker = "      - name: Build native app\n"
    cache = """      - name: Cache verified Whisper runtime\n        uses: actions/cache@v4\n        with:\n          path: .cache/full-mac-whisper-${{ matrix.arch }}\n          key: whisper-${{ runner.os }}-${{ matrix.arch }}-${{ hashFiles('scripts/full_mac_transcription_runtime.env') }}\n"""
    text = replace_once(text, marker, cache + marker, "Full Mac Whisper cache")
env_anchor = '          FULL_MAC_FFMPEG_CACHE_DIR: ${{ github.workspace }}/.cache/full-mac-media-${{ matrix.arch }}\n'
if "FULL_MAC_WHISPER_CACHE_DIR:" not in text:
    text = replace_once(text, env_anchor, env_anchor + '          FULL_MAC_WHISPER_CACHE_DIR: ${{ github.workspace }}/.cache/full-mac-whisper-${{ matrix.arch }}\n', "Full Mac Whisper env")
chmod_old = "chmod +x scripts/bootstrap_full_mac_python.sh scripts/build_embedded_ffmpeg.sh scripts/build_full_mac_app.sh scripts/audit_full_mac_app.sh"
chmod_new = chmod_old + " scripts/build_embedded_whisper.sh scripts/audit_embedded_whisper.sh scripts/smoke_full_mac_transcription.sh"
if "scripts/build_embedded_whisper.sh scripts/audit_embedded_whisper.sh" not in text:
    text = replace_once(text, chmod_old, chmod_new, "Full Mac chmod")
if "Audit embedded local transcription runtime" not in text:
    text = replace_once(
        text,
        "      - name: Smoke boot and render through bundled API\n",
        '      - name: Audit embedded local transcription runtime\n        shell: bash\n        run: bash scripts/audit_embedded_whisper.sh "dist/Binario Marketing IA.app" "${{ matrix.arch }}"\n      - name: Smoke boot and render through bundled API\n',
        "Full Mac Whisper audit",
    )
# Add browser module checks after the existing pro-media check; do not depend on a historical visual-gate anchor.
if '"$BASE/transcription.js"' not in text:
    anchor = '          /usr/bin/grep -q \'ensureActiveProxy\' "$RUNNER_TEMP/pro-media.js"\n'
    addition = anchor + '          /usr/bin/curl --fail --silent "$BASE/visual-timeline.js" > "$RUNNER_TEMP/visual-timeline.js"\n          /usr/bin/grep -q \'reorder_to\' "$RUNNER_TEMP/visual-timeline.js"\n          /usr/bin/curl --fail --silent "$BASE/transcription.js" > "$RUNNER_TEMP/transcription.js"\n          /usr/bin/grep -q \'startTranscription\' "$RUNNER_TEMP/transcription.js"\n          /usr/bin/curl --fail --silent "$BASE/clipper-modes.js" > "$RUNNER_TEMP/clipper-modes.js"\n          /usr/bin/grep -q \'clipperModePayload\' "$RUNNER_TEMP/clipper-modes.js"\n'
    text = replace_once(text, anchor, addition, "Full Mac browser module checks")
seq = '          bash scripts/smoke_full_mac_sequence.sh "$BASE" "$PY" "$MEDIA" "$RUNNER_TEMP"\n'
if "smoke_full_mac_transcription.sh" not in text:
    text = replace_once(text, seq, seq + '          bash scripts/smoke_full_mac_transcription.sh "$BASE" "$PY" "$MEDIA" "$RUNNER_TEMP"\n', "Full Mac transcription smoke")
write(path, text)

# 8) Native transcription smoke also certifies the new narrative objective-duration path.
path = "scripts/smoke_full_mac_transcription.sh"
text = read(path)
text = text.replace("--data '{\"target_count\":1,\"min_duration\":1,\"max_duration\":30}'", "--data '{\"target_count\":1,\"min_duration\":1,\"max_duration\":30,\"mode\":\"objective\",\"target_duration\":8}'", 1)
old = "assert str(row.get('text','')).strip(),row\nprint('SMOKE PASS: automatic transcript-driven Clipper')"
new = "assert str(row.get('text','')).strip(),row\nassert row.get('tone') in {'educativo','accionable','narrativo','provocativo'},row\nassert isinstance(row.get('reasons'),list),row\nassert 'hook_score' in row and 'closure_score' in row and 'duration_fit' in row,row\nprint('SMOKE PASS: narrative objective-duration transcript-driven Clipper')"
if old in text:
    text = text.replace(old, new, 1)
write(path, text)

# 9) Align contracts with the actual segmented router and relative embedded resolver.
path = "tests/test_transcription_runtime_contract.py"
text = read(path)
text = text.replace("'runtime/transcription/bin/whisper-cli'", "'transcription/bin/whisper-cli'")
text = text.replace("'runtime/transcription/models'", "'transcription/models/ggml-tiny.bin'")
if "builder.index('build_embedded_whisper.sh')" not in text:
    text = text.replace("        self.assertIn('runtime/transcription',builder)\n", "        self.assertIn('runtime/transcription',builder)\n        self.assertLess(builder.index('build_embedded_whisper.sh'),builder.index('/usr/bin/codesign'))\n", 1)
write(path, text)

path = "tests/test_transcription_ui_contract.py"
text = read(path)
old = "for token in ('TranscriptionManager','transcriptions','transcription/segments','transcription/file','transcription/clips'):\n            self.assertIn(token,service)"
new = "for token in ('TranscriptionManager','transcriptions','[\\\"transcription\\\", \\\"segments\\\"]','[\\\"transcription\\\", \\\"file\\\"]','[\\\"transcription\\\", \\\"clips\\\"]'):\n            self.assertIn(token,service)"
if old in text:
    text = text.replace(old, new, 1)
write(path, text)

# 10) Make workflow hygiene a permanent source contract.
write(
    "tests/test_workflow_hygiene.py",
    '''import unittest\nfrom pathlib import Path\n\nROOT=Path(__file__).resolve().parents[1]\n\nclass WorkflowHygieneTests(unittest.TestCase):\n    def test_only_canonical_product_workflows_are_tracked(self):\n        names={p.name for p in (ROOT/'.github/workflows').glob('*.yml')}\n        self.assertEqual(names,{'ci.yml','full-mac-app.yml','persistent-release.yml'})\n\nif __name__=='__main__':unittest.main()\n''',
)

# 11) Remove every historical source-mutating workflow. They must never reach main again.
workflows = ROOT / ".github" / "workflows"
canonical = {"ci.yml", "full-mac-app.yml", "persistent-release.yml"}
for candidate in workflows.glob("*.yml"):
    if candidate.name not in canonical:
        candidate.unlink()

# Remove this one-shot repair script too. The product tree must contain only durable source.
Path(__file__).unlink(missing_ok=True)

print("PASS: reconciled actual source for transcription + narrative Clipper; temporary workflows removed")
