# Post-W99 Pilot Health Summary

## Purpose

This increment adds one read-only local health view for the month-long MERCADEO APP pilot. It combines two evidence sources that already exist:

- Pilot Daily Receipt history (#193/#194);
- Structured Pilot Incident Log (#195).

It does not create a new business authority, readiness authority, persistence model, or execution engine. It is **not production readiness** and does not replace the Pilot Launch Gate, module owners, physical UAT, or release certification.

Frozen `main` remains exactly:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Development integration remains on `dev/post-w99-action-center` only.

## Inputs

The browser reads only the existing minimized local projections:

- `GET /api/pilot/daily-receipts?limit=90`
- `GET /api/pilot/incidents?status=ALL&limit=100`

There is **no new API** for pilot health and no new persisted health record. The status is recomputed on explicit open/refresh.

## Visible classification

The rules are intentionally simple, visible, and conservative. There is no AI scoring and no opaque weighted score.

### BLOQUEADO

Shown when at least one structured incident with severity `BLOCKING` is open.

### SIN EVIDENCIA

Shown when there is no daily receipt inside the rolling 30-day observation window and there is no stronger blocking condition.

### ATENCIÓN

Shown when evidence exists but at least one of these conditions remains:

- one or more `HIGH` incidents are open;
- at least one of the last 7 observed calendar days contains a receipt with pending launch checks;
- the current local date has no daily receipt;
- the current local date has a receipt that is not ready.

### ESTABLE

Shown only when all of these local evidence conditions are true:

- today has a daily receipt;
- today's receipt is ready;
- there are no open `BLOCKING` incidents;
- there are no open `HIGH` incidents;
- there are no attention receipts within the last 7 calendar days.

`ESTABLE` means only that the local pilot evidence is presently healthy. It does not assert provider availability, remote execution success, production readiness, physical UAT completion, release readiness, or commercial fitness.

## Metrics

The view displays a rolling 30-day summary derived in the browser:

- observed days;
- ready days;
- attention days;
- days without a receipt;
- current receipt streak ending today;
- open incidents;
- open blocking incidents;
- open high incidents;
- resolved incidents;
- attention receipts in the last 7 calendar days.

Missing daily receipts are treated as missing evidence, not as proof that the application failed.

## Operator flow

`Preparación piloto` receives one additional explicit action: `Salud del piloto`.

Opening it performs two local GET requests and renders the derived status. `Actualizar` repeats those two reads only when the operator asks. The panel can hand off to:

- `Seguimiento 30 días`;
- `Incidencias`.

The health view never creates a daily receipt or incident and never resolves an incident.

## Safety and authority boundaries

The increment adds no:

- POST, PATCH, PUT, or DELETE request;
- provider or Meta read/write;
- AI provider call or scoring;
- CRM, Inbox, campaign, content, publication, calendar, scheduler, or paid-media mutation;
- snapshot creation, restore, or delete;
- timer, polling loop, MutationObserver, unload hook, localStorage, or sessionStorage state;
- release, tag, deployment, or production authority.

The existing incident and receipt stores remain their own authorities. The browser projection cannot change them.

## Release boundary

The repository continues to use exactly three canonical workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

This increment advances `serve-dev` only. Canonical release `serve` and frozen W99 `main` remain separate.
