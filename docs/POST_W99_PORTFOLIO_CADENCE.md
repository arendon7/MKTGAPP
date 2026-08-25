# Post-W99 · Portfolio Cadence v2

## Purpose

Portfolio Cadence agrega semántica temporal explícita sobre la cola transversal ya ordenada por Portfolio Control Tower.

Responde únicamente:

- qué elementos ya fueron declarados por la fuente operativa como vencidos o para hoy;
- qué timestamps son incidentes u observaciones, no deadlines;
- qué leads tienen `received_at` válido y cuál es su antigüedad observada;
- qué trabajo requiere agenda humana;
- qué timestamps son futuros, inválidos o faltantes;
- si la cola expuesta por Portfolio Control Tower está truncada.

No calcula prioridad, no cambia el orden, no inventa fechas y no crea un task manager paralelo.

## Schema

`binario.marketing.portfolio-cadence.v2`

Endpoint GET-only:

`GET /api/portfolio-cadence`

La proyección consume únicamente `portfolio_control_tower()` del estado local.

## Temporal contract

### Deadlines

Solo se consideran `DEADLINE` los elementos que la fuente operativa ya clasificó como:

- `publication_overdue`
- `crm_overdue`
- `publication_today`
- `crm_today`

Cadence conserva la clasificación de la fuente, pero audita por separado la calidad del timestamp. Un deadline declarado por la fuente puede mostrar una anomalía temporal sin perder ni ganar prioridad.

### Incidents

`publication_failed` se representa como `INCIDENT_AT`. Su timestamp describe el incidente y nunca crea un nuevo vencimiento.

### Lead age

Los `lead_*` comerciales usan el `due_at` histórico de Action Center únicamente porque ese campo transporta el `received_at` original del lead.

Estados:

- `RECEIVED_LE_24H`
- `RECEIVED_24_72H`
- `RECEIVED_GT_72H`
- `FUTURE_RECEIVED_AT`
- `INVALID_RECEIVED_AT`
- `MISSING_RECEIVED_AT`

Un `received_at` futuro nunca se coerciona a cero horas. Su `age_hours` es `null` y queda registrado como anomalía. Lo mismo ocurre con timestamps inválidos o ausentes.

`received_at` nunca constituye deadline.

### Unscheduled and undated

`crm_unscheduled`, `needs_opportunity` y `needs_followup` son `UNSCHEDULED`: requieren agenda humana y no reciben una fecha inventada.

El resto del trabajo sin semántica suficiente queda como `UNDATED_ACTION`.

## Queue scope

Portfolio Control Tower puede reportar más elementos en `summary.queue_total` que los que expone en `queue`.

Cadence declara ambos valores:

- `parent_queue_total`
- `projected_queue_total`

Si el padre está truncado:

- `parent_queue_truncated=true`
- `completeness=PARTIAL_PARENT_QUEUE`

Cadence nunca inventa ni reconstruye los elementos no expuestos.

`first_explicit_deadline_in_priority_order` significa literalmente el primer deadline dentro del orden canónico existente. No pretende ser el deadline cronológicamente más cercano.

## Composition

`service_post_w99_portfolio_cadence_app` hereda el terminal actual `service_post_w99_evidence_observability_integrated_app`.

La secuencia acumulativa de navegador queda:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence`

Portfolio Cadence se carga después de `evidence-observability.js`; no reemplaza las superficies anteriores.

## Safety

- local state only;
- read-only projection;
- no provider reads;
- no provider writes;
- no business mutations;
- no AI generation;
- no automatic execution;
- no background polling;
- no forecasting;
- no causal inference;
- no reprioritization;
- no inferred deadlines.

## Frozen release boundary

Este incremento vive únicamente en la rama post-W99 de desarrollo.

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, el tree físico W99, `service.py`, `version.py`, builders, workflows, signing/notarization, el tag intent `v0.9.0` ni la autoridad de release/publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
