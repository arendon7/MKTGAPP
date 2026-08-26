# Post-W99 · Campaign MEDIA Candidate Selection Handoff

## Propósito

Campaign Execution Owner Cardinality Hardening conserva `AMBIGUOUS_TARGET + target_kind=MEDIA` cuando Wave64 indica `FINISH_CREATIVE` o `PREPARE_DISTRIBUTION` y existen varios creativos semánticamente elegibles. Esa ambigüedad es correcta: el sistema no debe convertir posición, orden, fecha o similitud en identidad.

Esta capa presenta esos `media_id` canónicos al operador y exige un **click humano explícito** para decidir cuál abrir en Creative Studio.

La composición actual se ejecuta después de **Setup Shadow Action Deduplication**. Por tanto, antes de cualquier handoff MEDIA, Action Center ya ha preservado `PLANNED_ONLY` como observación y ha retirado únicamente agregados SETUP cuya duplicación está demostrada. La selección MEDIA no altera ninguna de esas decisiones backend.

## Autoridad

- Wave64 conserva la autoridad sobre **qué acción** corresponde.
- Campaign Execution Owner Cardinality Hardening conserva la autoridad sobre si la identidad MEDIA es única o ambigua.
- Planned-Only Actionability Preservation conserva `CAMPAIGN/PLANNED_ONLY` fuera de `queue` y Today.
- Setup Shadow Action Deduplication conserva la autoridad de excluir únicamente agregados SETUP completamente cubiertos por acciones canónicas específicas.
- El backend continúa reportando `AMBIGUOUS_TARGET`; esta capa no persiste ni reescribe esa verdad.
- El click humano crea solo una copia efímera de navegación con el `media_id` elegido.
- Creative Studio W49 conserva edición y submit; W35 conserva la planificación de campaña/distribución.

## Condiciones de activación

El selector aparece únicamente cuando se cumplen simultáneamente:

1. `owner_resolution.state == AMBIGUOUS_TARGET`;
2. `target_kind == MEDIA`;
3. `owner_view == content`;
4. `source_code` es `FINISH_CREATIVE` o `PREPARE_DISTRIBUTION`;
5. hay al menos dos candidatos;
6. todos los candidatos tienen IDs canónicos no vacíos y únicos;
7. `candidate_count` coincide exactamente con el número de candidatos.

Cualquier divergencia falla cerrada y no produce destino exacto.

## Separación del selector histórico

`Campaign Execution Candidate Selector` mantiene su contrato de `PUBLICATION` / `PAID_DRAFT`. MEDIA permanece en una capa separada posterior porque esta ambigüedad nace específicamente del cardinality hardening de creativos.

No se amplía silenciosamente el selector histórico y no se crea una autoridad genérica de “escoger cualquier objeto”.

## Navegación efímera

La fila backend recibida no se muta. Después de `HUMAN_CLICK`, la copia de navegación conserva:

- `source_owner_resolution`: la resolución original `AMBIGUOUS_TARGET`;
- `explicit_media_selection.selected_by=HUMAN_CLICK`;
- `persisted=false`;
- `priority_inferred=false`;
- `recommendation_made=false`;
- `owner_resolution.state=EXACT_TARGET` únicamente en la copia;
- `navigation_only=true`;
- el `target_id` y `action.media_id` elegidos.

No se usa `localStorage`, `sessionStorage` ni ningún store de negocio.

## Today / Execution Return

Si la acción se abre desde Today y corresponde al contexto de retorno activo:

1. se elimina la captura provisional antes de mostrar candidatos;
2. no se registra destino mientras no exista elección humana;
3. tras el click se recaptura únicamente la copia exacta de navegación;
4. el owner canónico ejecuta o edita mediante sus controles existentes.

Cambio de empresa, refresh, `pagehide` o `Escape` invalidan/cierra la selección sin convertirla en estado de negocio.

## UX

- `FINISH_CREATIVE`: **¿Qué creativo quieres completar?**
- `PREPARE_DISTRIBUTION`: **¿Qué creativo quieres preparar para distribución?**

Cada opción muestra nombre, `media_id` y metadata disponible. Los candidatos se muestran en el orden recibido: no se ordenan, puntúan ni recomiendan.

## Composición acumulativa final

Runtime:

`Campaign MEDIA Candidate Selection Handoff → Setup Shadow Action Deduplication → Planned-Only Actionability Preservation → Campaign Execution Owner Cardinality Hardening → Campaign Coordinate Recovery Guidance → … → Today`

Browser:

`… → Campaign Coordinate Recovery Guidance → Campaign Execution Owner Cardinality Hardening → Planned-Only Actionability Preservation → Campaign MEDIA Candidate Selection Handoff`

Setup Shadow es backend-only; por eso no aparece como asset en la cadena browser. El servicio MEDIA hereda `service_post_w99_setup_shadow_action_deduplication_app` y añade su loader al servir `/planned-only-actionability.js`, preservando tanto la transformación backend como el último adapter browser preexistente.

## Invariants combinados

La versión final debe demostrar simultáneamente:

- `PLANNED_ONLY` permanece observacional y fuera de Today;
- los SETUP shadowed permanecen en `shadowed_actions` y fuera de Today;
- la deduplicación PAID sigue exigiendo cardinalidad fail-closed;
- las acciones CAMPAIGN específicas nunca se eliminan;
- múltiples MEDIA elegibles permanecen `AMBIGUOUS_TARGET` en backend;
- el browser no selecciona MEDIA hasta `HUMAN_CLICK`;
- la selección no persiste ni ejecuta submit/publicación/pauta;
- Action Center y Today no son repriorizados por esta capa.

## Seguridad

La selección MEDIA es browser-only y zero-transport. No añade endpoint de negocio, `POST/PATCH/PUT/DELETE`, provider read/write, polling, IA, auto-selection, `.click()` sintético, `dispatchEvent()`, autosave, publicación ni activación de pauta.

## Frozen release boundary

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, el candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni autoridad de release/publicación.

La physical UAT real continúa pendiente. **No constituye W100**, release candidate, Physical-UAT PASS, release authority, publication authority ni production-ready.
