# Post-W99 · Campaign Execution Owner Cardinality Hardening

## Propósito

Esta capa endurece dos límites del `Campaign Execution Owner Relay` sin reemplazarlo ni modificar sus ocho archivos certificados.

1. Un `media_id` que Wave 64 obtuvo por posición de lista no se convierte en identidad final únicamente porque ese ID exista.
2. Los formularios mutables de W49 y W35 conservan el invariant de `CONTROL_GROUP` introducido por el hardening previo: exactamente un submit canónico y habilitado.

La capa es terminal únicamente en `serve-dev`; `serve` canónico permanece intacto.

## Autoridades preservadas

- Wave 64 sigue siendo autoridad de **qué acción** corresponde.
- Campaign Execution Owner Relay sigue resolviendo publicación, calendario, pauta y Action Center.
- Creative Store / Campaign Store siguen siendo autoridad de identidad y mutación.
- Contextual Control Handoff sigue definiendo la semántica de `CONTROL_GROUP`.
- Esta capa solo restringe cuándo puede afirmarse `EXACT_TARGET` o `CONTROL_RESOLVED`.

## Cardinalidad semántica de MEDIA

### `FINISH_CREATIVE`

Candidatos elegibles:

- creativos vinculados a la campaña cuyo `effective_stage` **no** sea `READY`, `SCHEDULED`, `PUBLISHED`, `PAID` ni `ARCHIVED`.

Reglas:

- 0 candidatos → `NO_TARGET`;
- más de 1 → `AMBIGUOUS_TARGET`, aunque W64 haya incluido el ID del primero;
- exactamente 1 → solo `EXACT_TARGET` si el `media_id` W64 coincide con ese candidato único;
- candidato único + `media_id` distinto/ausente → `NO_TARGET`.

### `PREPARE_DISTRIBUTION`

Candidatos elegibles:

- creativos vinculados cuyo `effective_stage` sea `READY`, `SCHEDULED`, `PUBLISHED` o `PAID`.

Se aplican las mismas reglas de cardinalidad y coincidencia exacta.

### Por qué

W64 puede usar el primer elemento de una lista para hacer navegable una recomendación. Eso es válido como UX de owner, pero la posición no es evidencia suficiente para declarar que ese media es el único owner causal cuando existen varias piezas semánticamente válidas.

El hardening no cambia W64 ni reordena nada: simplemente impide elevar esa elección posicional a autoridad de identidad.

## Preservación del invariant CONTROL_GROUP

El relay de campaña se carga después de Contextual Control Handoff y puede interceptar su resolución. Por eso esta capa terminal vuelve a exigir el invariant fuerte en los dos formularios que representan una mutación con submit canónico único.

### W49 · FINISH_CREATIVE

Solo puede quedar `CONTROL_RESOLVED` cuando:

- el `media_id` exacto sigue seleccionado;
- existe un único `.w49-editor form.w49-form`;
- dentro del grupo existe exactamente un `Guardar ficha creativa`;
- ese submit está habilitado.

El usuario conserva la decisión de cambiar el campo Estado —por ejemplo a `Lista`—. La capa no cambia estado ni dispara submit.

### W35 · DEFINE_CHANNELS

Solo puede quedar `CONTROL_RESOLVED` cuando:

- la campaña exacta sigue seleccionada;
- existe un único `.campaign-form`;
- dentro del grupo existe exactamente un `Guardar cambios`;
- ese submit está habilitado.

Canales, estado y guardado siguen siendo decisiones humanas del owner W35.

## Grupos deliberadamente multi-opción

No se endurecen como submit único:

- publicación W42: `Guardar nueva versión` / `Cancelar publicación`;
- distribución W49: `Preparar Facebook` / `Preparar Instagram` / `Enviar a Pauta`;
- pauta W48: `Crear en Meta · PAUSED` / `Cancelar borrador`.

Son grupos de decisión humana, no formularios con un único submit canónico.

## Composición

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Owner Cardinality Hardening`

El nuevo terminal es `service_post_w99_campaign_execution_owner_cardinality_hardening_app`, que hereda `service_post_w99_campaign_execution_owner_relay_app`.

## Seguridad

La capa no añade:

- endpoints de negocio;
- POST/PATCH/PUT/DELETE;
- provider reads o writes;
- IA;
- polling;
- `.click()` / `dispatchEvent()`;
- selección por título, similitud, fecha o posición;
- auto-save, auto-ready, auto-publish ni auto-activate.

Action Center conserva su identidad, prioridad, rank, urgency, due semantics y orden. El método heredado llama dinámicamente a la resolución endurecida y únicamente `EXACT_TARGET` puede mejorar navegación.

## Frozen release boundary

Este hardening vive solo en desarrollo post-W99.

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni autoridad de release/publicación.

La physical UAT real continúa pendiente. No constituye W100, release candidate, physical-UAT PASS, release authority, publication authority ni production-ready.
