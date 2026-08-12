# FULL MAC build from canonical Git source

The Mac application is derived directly from a Git commit. No Wave ZIP is an input.

## Reproducibility chain

1. checkout exact commit;
2. download architecture-specific CPython 3.12.13 from the pinned upstream release;
3. verify its SHA-256 before extraction;
4. copy canonical `src/`, `apps/` and `web/` into the bundle;
5. write Git SHA + architecture into `BUILD_PROVENANCE.json`;
6. create a launcher that executes only the bundled interpreter with `-I -B`;
7. ad-hoc codesign for local execution;
8. audit bundle structure and 12/12 app discovery;
9. boot the bundled service and pass `/api/health` + `/api/apps` smoke tests;
10. ZIP the `.app`, hash the ZIP and upload both as CI artifacts.

## Native architectures

- `macos-15` → Apple Silicon / arm64;
- `macos-15-intel` → Intel / x86_64.

The bootstrap explicitly rejects cross-architecture verification. This prevents a build from claiming an architecture it did not execute natively.

## Local build for development

```bash
scripts/build_full_mac_app.sh --arch "$(uname -m)"
scripts/audit_full_mac_app.sh "dist/Binario Marketing IA.app"
```

Generated `.app`/ZIP files remain ignored by Git; the source and builder are canonical.
