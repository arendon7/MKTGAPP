# Post-W99 · Calendar Background Scheduler Control

## Product behavior

The global `Calendario` surface now exposes the local macOS background scheduling state before the editorial publication list.

The card shows:

- whether the capability is supported on the current platform;
- whether the per-user LaunchAgent is installed;
- whether `launchd` currently reports it loaded;
- whether its app/runtime references are stale;
- the configured 60-second review interval;
- the latest secret-free worker receipt when available.

## Explicit actions

The UI never enables background execution on page load.

The operator must explicitly choose one of these actions:

- `Activar en este Mac`;
- `Reinstalar` when paths are stale or the agent is stopped;
- `Desactivar` / `Eliminar configuración`.

Enable and disable both require a browser confirmation before the local mutation endpoint is called.

## Local API

Read-only status:

`GET /api/social/background`

Explicit enable:

`POST /api/social/background/install`

Explicit disable:

`DELETE /api/social/background`

The endpoints are loopback product endpoints only. They do not add a public or cloud control plane.

## Authority boundary

Activating the background scheduler does **not** authorize new content. It can process only publications already present in the existing durable queue with `QUEUED` status and due scheduling.

No AI generation, draft approval, account selection, campaign activation or new publication creation is performed by the background integration.

## Frozen boundary

Canonical `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` remains untouched.

This remains post-W99 development work and **No es W100**.
