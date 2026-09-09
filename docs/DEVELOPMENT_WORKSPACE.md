# Development workspace · VS Code + Google Antigravity

## Objective

Open the repository as a normal local development workspace and run the isolated post-W99 application without touching the frozen W99 release candidate.

The canonical development runtime is:

```bash
PYTHONPATH=src python3 -m binario_marketing.cli serve-dev --host 127.0.0.1 --port 8766 --open
```

This resolves through `service_post_w99_dev_app` and therefore includes the cumulative post-W99 product chain while `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` remains unchanged.

## VS Code

Prerequisites:

- Python 3.12 or newer.
- VS Code with the Python extension.
- Open the repository root, not only `src/` or `web/`.

The repository includes:

- `.vscode/tasks.json`
  - `MKTGAPP: Serve Dev`
  - `MKTGAPP: Test All`
  - `MKTGAPP: Runtime Diagnostics`
  - `MKTGAPP: Meta Status (read-only)`
- `.vscode/launch.json`
  - `MKTGAPP: Debug Serve Dev`
- `.vscode/extensions.json`
  - Python/debugpy and Google Antigravity recommendations.

Normal flow:

1. Open the repository root.
2. Run `MKTGAPP: Test All`.
3. Run `MKTGAPP: Serve Dev` or start `MKTGAPP: Debug Serve Dev`.
4. The local application opens on `http://127.0.0.1:8766/`.

No Meta token is required to open the application. Provider-dependent functions remain unavailable until their existing explicit credential flow is configured.

## Google Antigravity

Antigravity can work either through its VS Code extension or through an Antigravity Project that points to this Git checkout.

Repository-level guidance is stored in `AGENTS.md`; agents should read and preserve it before making changes. In particular:

- do not modify frozen `main` while W99 physical UAT is open;
- branch from `dev/post-w99-action-center` for post-W99 product work;
- use `serve-dev` rather than the frozen release runtime;
- preserve human-governed provider and AI authority boundaries;
- run the complete test suite before proposing integration.

For isolated or multi-file agent tasks, prefer a new worktree based on the current post-W99 development branch. For small supervised edits, Local Mode is acceptable.

## Branch workflow

```text
main (W99 frozen)
        │
        └── dev/post-w99-action-center
                 │
                 ├── feature/...
                 ├── feature/...
                 └── feature/...
```

Feature PRs target `dev/post-w99-action-center`. Do not retarget them to `main` merely to make them visible to the release pipeline.

## Verification

Complete source suite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Runtime diagnostics:

```bash
PYTHONPATH=src python3 -m binario_marketing.cli runtime
```

Safe Meta readiness check:

```bash
PYTHONPATH=src python3 -m binario_marketing.cli meta-status
```

The development workspace configuration contains no credentials and does not perform social publishing, replies, CRM mutation, paid-media mutation, or AI generation by itself.
