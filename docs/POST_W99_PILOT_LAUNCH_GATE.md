# Post-W99 Pilot Launch Gate

## Purpose

This increment gives MERCADEO APP one operator-facing place to decide whether the local pilot is ready to start. It consolidates existing post-W99 evidence instead of creating a second readiness or execution engine.

The gate is **not production readiness**, is not release authority, and does not alter the physical W99 release route.

Frozen `main` remains exactly:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Development integration remains on `dev/post-w99-action-center` only.

## Five launch controls

1. **Aplicación local** — reuses `/api/pilot-session/status` and requires the backend plus the four base local store reads to be healthy.
2. **Empresas** — reuses the existing `/api/portfolio/companies` W50 projection. At least one company must exist and there must be no local-state error.
3. **Recorrido observado** — reuses `pilotJourneyReport()` and requires the routes for the current operator mode to have been manually opened and rendered during the session.
4. **Respaldo local** — requires at least one snapshot visible through Pilot Data Safety.
5. **Recuperación ensayada** — requires a successful #191 recovery rehearsal for the **same latest snapshot** during the current browser session.

Only when all five controls pass does the UI show `LISTO PARA PILOTO LOCAL`.

## W50 boundary

W50 remains the sole company readiness authority. The gate reads the existing portfolio projection and displays `fully_ready` and average readiness as context. It intentionally does **not** require every company to be 8/8 before a local pilot can start, because the pilot may begin with one company while other companies are still being configured.

The gate does not mutate W50 state and does not implement provider setup.

## Session-only recovery evidence

#191 now exposes the latest recovery rehearsal result in browser memory through `pilotRecoveryRehearsalReport()` and emits `post-w99-pilot-recovery-rehearsed`.

This evidence:
- is never written to `localStorage` or `sessionStorage`;
- is not persisted to application data;
- does not contain filesystem paths or hashes;
- must match the current latest snapshot id before the launch control can pass;
- disappears when the browser session is restarted.

## Explicit operator model

Opening `Preparación piloto` performs only the two existing local GET reads needed for runtime and company status. It does not automatically create a snapshot, run a recovery rehearsal, navigate the product, call Meta, invoke AI providers, publish, schedule, or mutate campaigns.

The operator must explicitly:
- visit the pilot journey routes;
- create a snapshot if none exists;
- press `Probar recuperación` to establish session evidence.

## Navigation consolidation

`Preparación piloto` becomes the primary top-level pilot control. The previous `Estado piloto`, `Recorrido piloto`, and `Respaldo local` top actions are suppressed from the top bar once the gate loads, but their existing panels/functions remain available from inside the gate.

No underlying authority is removed or duplicated.

## Safety and release boundaries

The gate adds:
- no `POST`, `PATCH`, or `DELETE` endpoint;
- no Meta/provider reads or mutations;
- no background polling;
- no workers;
- no restore/delete authority;
- no release/tag/publication authority.

The repository continues to have exactly three canonical workflows:
- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

A green Pilot Launch Gate means **local pilot ready**, not production ready, not physical UAT complete, and not permission to tag or release `v0.9.0`.
