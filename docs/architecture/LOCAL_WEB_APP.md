# Local Web App vertical slice

The canonical source includes a dependency-free local HTTP service and a versioned browser UI.

## Default safety boundary

`binario-marketing serve` binds to `127.0.0.1:8765`. A non-loopback bind is refused unless the operator explicitly passes `--allow-network`.

## Persisted user state

User state is external to Git, by default under `~/Documents/Binario IA/`:

- `Projects/`: project registry and copied managed assets;
- `State/editor/`: persisted Editor sessions including undo/redo history;
- `State/workspace/`: projects, handoffs and append-only registries.

## File ingestion

The normal UI uses a browser file picker. File bodies are streamed directly to a managed project asset in 1 MiB chunks, never buffered as a whole video in memory. Every new asset records byte size and SHA-256. The legacy/local automation route that imports by filesystem path remains available through the JSON API but is no longer the primary UI.

Uploads require a known `Content-Length`, are capped at 50 GiB per request, and partial files are removed if the body ends early.

## Current vertical flow

1. create project;
2. select one or more files in the browser and stream them into managed assets;
3. add project assets to the Editor timeline;
4. split, lock, delete, undo, redo, reset and change aspect ratio;
5. run the social clipper from transcript segments;
6. create a handoff from Editor to another app;
7. inspect Unified Timeline events.

The browser UI uses the same JSON/raw-upload API covered by end-to-end HTTP tests.
