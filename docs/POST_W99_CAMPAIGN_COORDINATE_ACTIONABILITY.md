# Post-W99 · Campaign Coordinate Actionability Preservation

## Propósito

Wave64 ya distingue entre acciones que requieren intervención y el fallback `COORDINATE`: cuando llega a `COORDINATE`, publica `requires_action=False`. Sin embargo, el compositor original de Action Center crea todas sus filas con `requires_human_action=True`. Ese desacople puede convertir un estado puramente coordinativo u observacional en una falsa tarea de Action Center y de Hoy.

Esta capa preserva de extremo a extremo la semántica de Wave64 sin cambiar su autoridad de siguiente acción.

## Regla fail-closed

Toda fila `CAMPAIGN/coordinate` se considera **no accionable por defecto**.

Solo permanece en `queue` y puede entrar a Today cuando **Campaign Coordinate Recovery Guidance** ya demostró un `EXACT_RECOVERY_OWNER` completo y verificable. La prueba exige simultáneamente:

1. `coordinate_state.state = ONLY_CANCELLED_DISTRIBUTION_REMAINS`;
2. `coordinate_recovery.source_coordinate_state = ONLY_CANCELLED_DISTRIBUTION_REMAINS`;
3. `coordinate_recovery.state = EXACT_RECOVERY_OWNER`;
4. `intent = CREATE_NEW_DISTRIBUTION_FROM_CANCELLED_LINEAGE`;
5. `owner_view = content`;
6. `target_kind = MEDIA`;
7. `target_id` canónico no vacío;
8. `action.view = content`;
9. `action.media_id == target_id`;
10. exactamente un candidato `source_media`, con ese mismo ID;
11. al menos un `recovery_control` canónico, único y perteneciente al conjunto certificado:
   - `PREPARE_FACEBOOK`;
   - `PREPARE_INSTAGRAM`;
   - `SEND_TO_PAID`.

Cualquier ausencia, contradicción, cardinalidad distinta, control desconocido o estado futuro no certificado falla cerrado.

## Estados observacionales

Los `COORDINATE` que no superan la prueba anterior salen de la cola y pasan a `observations`. Esto incluye, entre otros:

- `PUBLICATION_IN_FLIGHT`, incluso cuando existe un `EXACT_EXISTING_OWNER`: abrir la publicación sirve para observarla, no para completar, reintentar o mutar el tránsito remoto;
- `AMBIGUOUS_EXISTING_OWNER`;
- `RECOVERY_INVARIANT_GAP`;
- `RECOVERY_OWNER_GAP`;
- `AMBIGUOUS_RECOVERY_OWNER`;
- `DIAGNOSTIC_ONLY`;
- `COORDINATE_INVARIANT_DRIFT`;
- `UNCLASSIFIED_COORDINATION_STATE`;
- cualquier estado futuro no reconocido.

La observación conserva la fila, `coordinate_state`, `coordinate_recovery`, identidad de campaña y navegación existente. Se marca:

- `requires_human_action=false`;
- `blocking=false`;
- `actionability.state=NON_ACTIONABLE_COORDINATE`;
- `executable=false`;
- `today_eligible=false`;
- `owner_navigation_allowed=true`.

No se interpreta ausencia de tarea como finalización de campaña.

## Recuperación exacta

`EXACT_RECOVERY_OWNER` no concede una nueva autoridad de negocio. Solo mantiene accionable una fila porque #137 ya demostró:

- lineage local canónica desde los objetos cancelados;
- un único creativo administrado;
- un `media_id` exacto;
- al menos un control W49 certificado compatible con esa lineage.

Los controles existentes de W49 continúan siendo los únicos owners de mutación y requieren interacción humana.

## Relación con #136 y #137

- **Campaign Coordinate State Decomposition** (#136) sigue siendo la autoridad diagnóstica de `COORDINATE`.
- **Campaign Coordinate Recovery Guidance** (#137) sigue siendo la autoridad para convertir una parte del diagnóstico en navegación exact-lineage.
- Esta capa no recalcula esos estados, no cambia sus candidatos y no crea recovery adicional. Solo decide si la proyección ya demostrada representa una tarea humana real o una observación.

## Today

Today deriva su plan desde `self.action_center()`. Por eso la corrección ocurre antes de la proyección de Hoy:

- los `COORDINATE` observacionales nunca entran al plan;
- una recuperación exacta sí puede permanecer en el plan;
- el orden relativo de todas las acciones restantes se conserva.

## UI

El browser añade una sección **COORDINACIÓN · OBSERVACIONES** dentro de Action Center.

La UI:

- lee únicamente `observations`;
- muestra estado coordinativo y estado de recovery;
- permite `Ver contexto` mediante la navegación existente;
- no eleva la observación a tarea;
- no persiste selección;
- no ejecuta controles.

## Seguridad

La capa es local y read-only respecto del negocio:

- no añade `POST`, `PATCH`, `PUT` ni `DELETE`;
- no añade provider read/write;
- no genera IA;
- no hace polling;
- no usa `fetch`, `opsApi`, `sendBeacon`, clicks sintéticos ni `dispatchEvent`;
- no publica, programa, activa pauta, reintenta publicaciones ni resucita objetos cancelados;
- no reprioriza acciones.

## Composición

Runtime:

`Campaign Coordinate Actionability Preservation → Campaign MEDIA Candidate Selection Handoff → Setup Shadow Action Deduplication → Planned-Only Actionability Preservation → Campaign Execution Owner Cardinality Hardening → Campaign Coordinate Recovery Guidance → Campaign Coordinate State Decomposition → … → Today`

Browser tail:

`… → Planned-Only Actionability Preservation → Campaign MEDIA Candidate Selection Handoff → Campaign Coordinate Actionability Preservation`

## Frozen release boundary

Esta capa modifica exclusivamente `serve-dev` en `dev/post-w99-action-center`.

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, el candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni la autoridad de release/publicación.

La Physical UAT real en Apple Silicon continúa pendiente. **No constituye W100, Physical-UAT PASS, release authority, publication authority ni production-ready.**
