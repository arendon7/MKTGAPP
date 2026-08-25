# Post-W99 · Campaign Execution Owner Cardinality Hardening

## Propósito

Esta capa endurece dos límites del `Campaign Execution Owner Relay` sin reemplazarlo y sin modificar las capas post-W99 ya certificadas que lo envuelven.

1. Un `media_id` que Wave 64 obtuvo por posición de lista no se convierte en identidad final únicamente porque ese ID exista.
2. Los formularios mutables de W49 y W35 conservan el invariant de `CONTROL_GROUP`: exactamente un submit canónico y habilitado.

La capa es terminal únicamente en `serve-dev`; `serve` canónico permanece intacto.

## Reconciliación con el trunk actual

Este hardening se reconstruyó sobre `dev/post-w99-action-center@f1b81c2d548de968f82cf44b78b0a3520360c07d`, después de la integración de **Campaign Coordinate Recovery Guidance**.

No sustituye los incrementos ya integrados: Campaign Execution Candidate Selector, Campaign Creative Creation Intent Handoff, Campaign Coordinate State Decomposition ni Campaign Coordinate Recovery Guidance. El runtime hereda `service_post_w99_campaign_coordinate_recovery_guidance_app`; esa capa conserva la recuperación exact-lineage de `COORDINATE`. Este hardening solo restringe la identidad MEDIA para los códigos W64 normales `FINISH_CREATIVE` y `PREPARE_DISTRIBUTION`.

## Autoridades preservadas

- Wave 64 sigue siendo autoridad de **qué acción** corresponde.
- Campaign Execution Owner Relay sigue resolviendo publication/calendar/paid y owner context.
- Candidate Selector sigue limitado a ambigüedades `PUBLICATION` y `PAID_DRAFT`.
- Creative Creation Intent Handoff sigue manejando `CREATE_CREATIVE + OWNER_ONLY`.
- Coordinate State Decomposition sigue diagnosticando `COORDINATE`.
- Coordinate Recovery Guidance conserva la lineage y los controles humanos de recuperación para `COORDINATE`.
- Creative Store / Campaign Store siguen siendo autoridad de identidad y mutación.
- Contextual Control Handoff sigue definiendo la semántica de `CONTROL_GROUP`.

## Cardinalidad semántica de MEDIA

### `FINISH_CREATIVE`

Son elegibles los creativos vinculados cuyo `effective_stage` no sea `READY`, `SCHEDULED`, `PUBLISHED`, `PAID` ni `ARCHIVED`.

### `PREPARE_DISTRIBUTION`

Son elegibles los creativos vinculados cuyo `effective_stage` sea `READY`, `SCHEDULED`, `PUBLISHED` o `PAID`.

Para ambos códigos:

- 0 candidatos → `NO_TARGET`;
- más de 1 → `AMBIGUOUS_TARGET`, incluso si W64 incluyó el ID del primero;
- exactamente 1 → `EXACT_TARGET` solo si el `media_id` W64 coincide;
- candidato único con ID ausente/distinto → `NO_TARGET`.

La posición de una lista puede servir como UX provisional de navegación, pero no como autoridad de identidad final.

## Relación con `COORDINATE`

El hardening no reinterpreta `COORDINATE` y delega cualquier resolución no MEDIA al runtime heredado. Por tanto:

- `PUBLICATION_IN_FLIGHT` continúa siendo observación exacta sin retry;
- recuperación desde objetos `CANCELLED` continúa usando lineage canónica y controles W49 humanos;
- los objetos cancelados permanecen terminales;
- la ambigüedad de recuperación sigue fallando cerrada.

## Preservación del invariant `CONTROL_GROUP`

### W49 · `FINISH_CREATIVE`

Solo puede quedar `CONTROL_RESOLVED` cuando el `media_id` exacto sigue seleccionado, existe un único `.w49-editor form.w49-form`, existe exactamente un `Guardar ficha creativa` habilitado y el usuario ejecuta el submit.

### W35 · `DEFINE_CHANNELS`

Solo puede quedar `CONTROL_RESOLVED` cuando la campaña exacta sigue seleccionada, existe un único `.campaign-form`, existe exactamente un `Guardar cambios` habilitado y el usuario ejecuta el submit.

No se convierten en submit único los grupos deliberadamente multi-opción de W42, distribución W49, pauta W48 ni Coordinate Recovery Guidance.

## Composición

Runtime:

`Campaign Execution Owner Cardinality Hardening → Campaign Coordinate Recovery Guidance → Campaign Coordinate State Decomposition → Campaign Creative Creation Intent Handoff → Campaign Execution Candidate Selector → Campaign Execution Owner Relay → … → Today`

Browser:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance → Campaign Execution Owner Cardinality Hardening`

## Seguridad

La capa no añade endpoint de negocio, `POST/PATCH/PUT/DELETE`, provider read/write, IA, polling, `.click()` sintético, `dispatchEvent()`, auto-save, auto-ready, auto-publish ni auto-activate. Action Center conserva identidad, prioridad, rank, urgency, due semantics y orden.

## Frozen release boundary

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni autoridad de release/publicación.

La physical UAT real continúa pendiente. No constituye W100, release candidate, Physical-UAT PASS, release authority, publication authority ni production-ready.
