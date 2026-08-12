# FULL MAC build from canonical Git source

The Mac application is derived directly from a Git commit. No Wave ZIP is an input.

## Reproducibility chain

1. checkout exact MKTGAPP commit;
2. download architecture-specific CPython 3.12.13 from the pinned python-build-standalone release and verify SHA-256;
3. fetch the signed FFmpeg `n8.1.2` release commit `38b88335f99e76ed89ff3c93f877fdefce736c13` from the official FFmpeg repository;
4. build FFmpeg/FFprobe natively with autodetected external libraries disabled, VideoToolbox + AudioToolbox enabled, and no GPL/nonfree switch;
5. reject media binaries linked to Homebrew, `/usr/local`, runner home or temporary build paths;
6. preserve upstream LGPL notices in the media runtime;
7. copy canonical `src/`, `apps/` and `web/` into the bundle;
8. write Git SHA + architecture + runtime provenance into the bundle;
9. launch only the bundled Python/FFmpeg/FFprobe runtimes;
10. audit structure, codesign and 12/12 app discovery;
11. generate a synthetic video with bundled FFmpeg and probe it with bundled FFprobe;
12. boot the bundled service and verify `/api/health`, `/api/apps` and Runtime Center locations;
13. ZIP the `.app`, hash the ZIP and upload both as CI artifacts.

## Native architectures

- `macos-15` → Apple Silicon / arm64;
- `macos-15-intel` → Intel / x86_64.

Both Python and FFmpeg builders reject cross-architecture claims. FFmpeg x86_64 disables optional x86 assembly so the build does not depend on NASM/YASM being present on the runner.

## Media encoding policy

The default proprietary-library dependency `libx264` has been removed. On macOS the Editor prefers the native `h264_videotoolbox` encoder and retains the built-in MPEG-4 encoder as a capability fallback. Audio defaults to FFmpeg's AAC encoder.

## CI cache

The compiled media runtime is cached by FFmpeg version, exact source commit and architecture. Cache entries are reused only after provenance and executable self-checks pass.

## Local build for development

```bash
scripts/build_full_mac_app.sh --arch "$(uname -m)"
scripts/audit_full_mac_app.sh "dist/Binario Marketing IA.app"
```

Generated `.app`/ZIP files remain ignored by Git; source, runtime pins and build scripts are canonical.
