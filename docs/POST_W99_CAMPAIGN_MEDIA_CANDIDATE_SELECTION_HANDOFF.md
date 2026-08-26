# Post-W99 · Campaign MEDIA Candidate Selection Handoff

## Propósito

Esta capa cierra de forma explícita el caso que aparece después de **Campaign Execution Owner Cardinality Hardening**: cuando Wave64 indica `FINISH_CREATIVE` o `PREPARE_DISTRIBUTION`, pero existen varios creativos semánticamente elegibles, el backend conserva correctamente `AMBIGUOUS_TARGET + target_kind=MEDIA` y no convierte el primer elemento de una lista en identidad.

La solución no vuelve a introducir una heurística. Presenta los `media_id` canónicos disponibles y exige un **click humano explícito** para elegir cuál abrir en Creative Studio.

## Autoridad y alcance

- Wave64 conserva la autoridad sobre **qué acción** corresponde.
- Campaign Execution Owner Cardinality Hardening conserva la autoridad sobre si la identidad MEDIA es única o ambigua.
- El backend continúa reportando `AMBIGUOUS_TARGET`; esta capa no reescribe ni persiste esa verdad.
- El click humano solo crea una copia efímera de navegación para atravesar el stack browser con un `media_id` exacto.
- Creative Studio W49 conserva identidad, estado, edición y submit final.
- Contextual Control Handoff + Cardinality Hardening conservan el invariant del submit canónico.

El selector se activa únicamente cuando:

1. `owner_resolution.state == AMBIGUOUS_TARGET`;
2. `target_kind == MEDIA`;
3. `owner_view == content`;
4. `source_code` es `FINISH_CREATIVE` o `PREPARE_DISTRIBUTION`;
5. hay al menos dos candidatos;
6. cada candidato tiene `media_id` no vacío y único;
7. `candidate_count` coincide exactamente con la lista recibida.

Cualquier divergencia falla cerrada.

## Separación del selector histórico

`Campaign Execution Candidate Selector` mantiene su contrato original para `PUBLICATION` y `PAID_DRAFT`. Esta capa no modifica ese archivo ni amplía silenciosamente su autoridad.

La selección MEDIA es un handoff nuevo y posterior porque su ambigüedad nace del hardening semántico integrado después de aquel selector histórico.

## Navegación efímera

Después del click humano se crea una copia de la fila, nunca se muta la fila backend recibida.

La copia conserva:

- `source_owner_resolution`: resolución original `AMBIGUOUS_TARGET`;
- `explicit_media_selection`: evidencia de `HUMAN_CLICK`, `persisted=false`, `priority_inferred=false` y `recommendation_made=false`;
- `owner_resolution` de navegación marcado `navigation_only=true`, con el `target_id` elegido y un solo candidato;
- `action.view = content`;
- `action.media_id = <media_id elegido>`.

La resolución `navigation_only` existe únicamente para esa apertura. No afirma que el backend haya dejado de ser ambiguo, no cambia Action Center y no se almacena en `localStorage`, `sessionStorage` ni ningún store de negocio.

## Today / Execution Return

Si la acción se abrió desde Today y existe contexto de retorno para esa misma acción:

1. se elimina la captura provisional antes de mostrar el selector;
2. no se registra ningún destino mientras el usuario no elija;
3. después del click se captura la copia con el `media_id` exacto;
4. el flujo vuelve a usar los deep links y owners ya existentes.

Cambiar de empresa invalida el diálogo. Refresh, `pagehide` o `Escape` también lo cierran sin seleccionar nada.

## UX

Para `FINISH_CREATIVE` el diálogo pregunta **“¿Qué creativo quieres completar?”**.

Para `PREPARE_DISTRIBUTION` pregunta **“¿Qué creativo quieres preparar para distribución?”**.

Cada opción muestra nombre, `media_id` y estado cuando están disponibles. El orden recibido se conserva: no se ordena, no se puntúa y no representa recomendación.

## Composición

Runtime:

`Campaign MEDIA Candidate Selection Handoff → Campaign Execution Owner Cardinality Hardening → Campaign Coordinate Recovery Guidance → Campaign Coordinate State Decomposition → Campaign Creative Creation Intent Handoff → Campaign Execution Candidate Selector → Campaign Execution Owner Relay → … → Today`

Browser:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance → Campaign Execution Owner Cardinality Hardening → Campaign MEDIA Candidate Selection Handoff`

## Seguridad

La capa es browser-only y zero-transport. No añade endpoint de negocio, `POST/PATCH/PUT/DELETE`, provider read/write, polling, IA, auto-selection, `.click()` sintético, `dispatchEvent()`, autosave, cambio de estado, publicación ni activación de pauta.

El operador sigue ejecutando la mutación real en el owner canónico y mediante su submit humano.

## Frozen release boundary

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, el candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni autoridad de release/publicación.

La physical UAT real continúa pendiente. No constituye W100, release candidate, Physical-UAT PASS, release authority, publication authority ni production-ready.
