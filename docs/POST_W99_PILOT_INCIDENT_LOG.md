# Post-W99 Pilot Incident Log

## Purpose

This increment gives the month-long local pilot a small structured incident register. It exists to capture operational friction while MERCADEO APP is being used, without turning the pilot log into a repository for customer data, provider metadata, screenshots, credentials, or free-form notes.

The feature is **not production readiness**, issue-tracker synchronization, provider observability, automated remediation, or release authority.

Frozen `main` remains exactly:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Development integration remains on `dev/post-w99-action-center` only.

## Structured taxonomy

An incident opening accepts exactly four operator-selected values:
- local calendar date;
- module;
- category;
- severity.

Modules are a closed enum covering:
- Inicio;
- Hoy;
- Empresas;
- Contenido;
- Calendario;
- CRM;
- Mensajes;
- Campañas;
- Pauta;
- Resultados;
- Video Studio;
- IA;
- Respaldo.

Categories are a closed enum:
- Interfaz;
- Datos;
- Flujo de trabajo;
- Rendimiento;
- Integración;
- Arranque;
- Recuperación.

Severity is a closed enum:
- Baja;
- Media;
- Alta;
- Bloqueante.

There is **no free-form** title, description, note, comment or attachment field.

## Append-only event model

The durable store contains an append-only event stream.

Opening an incident appends an `OPENED` event. Resolving it appends a `RESOLVED` event tied to the exact generated incident id. The opening event is never edited or deleted.

The current incident projection is derived from those events:
- `OPEN` when an opening has no later valid resolution;
- `RESOLVED` after exactly one valid resolution event.

A second resolution fails closed. A resolution without a prior opening fails closed. Duplicate openings for the same id or malformed persisted sequences fail integrity validation.

## Operator flow

`Preparación piloto` gains two explicit controls:
- `Registrar incidencia`;
- `Incidencias`.

The registration surface uses only select controls for module, category and severity. `Registrar incidencia` performs one explicit local POST.

The history surface performs one explicit local GET. An open incident exposes `Marcar resuelta`, which performs one explicit local POST for that exact incident. There is no delete route.

The feature adds no timer, polling loop, MutationObserver, unload hook, localStorage, sessionStorage, background write, or automatic incident creation.

## Local API

Read:

`GET /api/pilot/incidents?status=ALL&limit=100`

Open:

`POST /api/pilot/incidents`

Resolve exact incident:

`POST /api/pilot/incidents/<incident_id>/resolve`

Both writes require the explicit local operator header:

`X-Mercadeo-Operator: pilot-incident-log`

The public projection exposes only generated local incident id, dates/timestamps, enum classifications, status and aggregate counts. Internal event ids are not exposed.

## Privacy and authority boundary

The log intentionally stores no:
- company id or company name;
- contact id, contact details or PII;
- message content;
- campaign/content/publication identifiers;
- provider ids, targeting or remote error payloads;
- URLs;
- access tokens, credentials or secrets;
- prompts or AI output;
- filesystem paths, hashes or file contents;
- screenshots or attachments;
- free-form operator text.

Registering or resolving an incident does not execute remediation. It does not publish, schedule, refresh Meta, modify CRM, change campaigns, edit content, restore a snapshot, or call AI.

There is no incident delete authority.

## Runtime composition

`service_post_w99_pilot_incident_log_app` extends the #194 month-tracker terminal. It adds the local incident store, bounded GET/POST routes and `pilot-incident-log.js`.

The loader is appended after `pilot-month-tracker.js`; `service_post_w99_dev_app` advances to the new terminal. Canonical `serve` remains frozen and separate.

The repository continues to contain exactly three canonical workflows:
- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

Physical Apple Silicon UAT and the W99 release path remain separate and unchanged.
