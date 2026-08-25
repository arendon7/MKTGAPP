# Post-W99 · Campaign Execution Owner Cardinality Hardening

## Propósito

Esta capa endurece dos límites del `Campaign Execution Owner Relay` sin reemplazarlo y sin modificar las capas post-W99 ya certificadas que hoy lo envuelven.

1. Un `media_id` que Wave 64 obtuvo por posición de lista no se convierte en identidad final únicamente porque ese ID exista.
2. Los formularios mutables de W49 y W35 conservan el invariant de `CONTROL_GROUP`: exactamente un submit canónico y habilitado.

La capa es terminal únicamente en `serve-dev`; `serve` canónico permanece intacto.

## Reconciliación con el trunk actual

Este hardening se reconstruyó sobre `dev/post-w99-action-center@d6b1211805bdc49d5c6edfd18d3a73f8b69c9345`.

No sustituye los incrementos ya integrados:

- Campaign Execution Candidate Selector;
- Campaign Creative Creation Intent Handoff;
- Campaign Coordinate State Decomposition.

El runtime hereda `service_post_w99_campaign_coordinate_state_decomposition_app`, que conserva toda esa cadena. Para la semántica de identidad MEDIA reutiliza únicamente las funciones de proyección del `Campaign Execution Owner Relay`.

## Autoridades preservadas

- Wave 64 sigue siendo autoridad de **qué acción** corresponde.
- Campaign Execution Owner Relay sigue resolviendo publicación, calendario, pauta y el owner context.
- Candidate Selector sigue manejando las ambigüedades humanas de `PUBLICATION` y `PAID_DRAFT`.
- Creative Creation Intent Handoff sigue manejando `CREATE_CREATIVE + OWNER_ONLY`.
- Coordinate State Decomposition sigue diagnosticando `COORDINATE` sin reescribir la acción.
- Creative Store / Campaign Store siguen siendo autoridad de identidad y mutación.
- Contextual Control Handoff sigue definiendo la semántica de `CONTROL_GROUP`.
- Esta capa solo restringe cuándo puede afirmarse `EXACT_TARGET` para MEDIA y cuándo un formulario mutable puede declararse `CONTROL_RESOLVED`.

## Cardinalidad semántica de MEDIA

### `FINISH_CREATIVE`

Candidatos elegibles:

- creativos vinculados a la campaña cuyo `effective_stage` no sea `READY`, `SCHEDULED`, `PUBLISHED`, `PAID` ni `ARCHIVED`.

Reglas:

- 0 candidatos → `NO_TARGET`;
- más de 1 → `AMBIGUOUS_TARGET`, aunque W64 haya incluido el ID de uno de ellos;
- exactamente 1 → solo `EXACT_TARGET` si el `media_id` W64 coincide con ese candidato único;
- candidato único + `media_id` distinto o ausente → `NO_TARGET`.

### `PREPARE_DISTRIBUTION`

Candidatos elegibles:

- creativos vinculados cuyo `effective_stage` sea `READY`, `SCHEDULED`, `PUBLISHED` o `PAID`.

Se aplican las mismas reglas de cardinalidad y coincidencia exacta.

### Razón

Wave 64 puede usar el primer elemento de una lista para hacer navegable una recomendación. Eso es válido como UX de owner, pero la posición no es evidencia suficiente para declarar que ese MEDIA es el único owner causal cuando existen varias piezas semánticamente válidas.

El hardening no cambia Wave 64 ni reordena Action Center. Impide elevar una elección posicional a autoridad de identidad.

## Relación con Candidate Selector

El Candidate Selector integrado antes de esta capa está deliberadamente limitado a ambigüedades `PUBLICATION` y `PAID_DRAFT`.

Por tanto, un `AMBIGUOUS_TARGET + MEDIA` producido por este hardening continúa fail-closed. No se habilita preventivamente una selección MEDIA nueva: una futura UX deberá definir su contrato humano específico sin reutilizar autoridad de otros tipos.

## Preservación del invariant `CONTROL_GROUP`

### W49 · `FINISH_CREATIVE`

Solo puede quedar `CONTROL_RESOLVED` cuando:

- el `media_id` exacto sigue seleccionado;
- existe un único `.w49-editor form.w49-form`;
- dentro del grupo existe exactamente un `Guardar ficha creativa`;
- ese submit está habilitado.

El usuario conserva la decisión de editar `Estado` y realizar el submit final.

### W35 · `DEFINE_CHANNELS`

Solo puede quedar `CONTROL_RESOLVED` cuando:

- la campaña exacta sigue seleccionada;
- existe un único `.campaign-form`;
- dentro del grupo existe exactamente un `Guardar cambios`;
- ese submit está habilitado.

Canales, estado y guardado siguen siendo decisiones humanas del owner W35.

## Grupos deliberadamente multi-opción

No se convierten en submit único:

- publicación W42: `Guardar nueva versión` / `Cancelar publicación`;
- distribución W49: Facebook / Instagram / Pauta;
- pauta W48: `Crear en Meta · PAUSED` / `Cancelar borrador`.

Son decisiones humanas, no formularios con un único submit canónico.

## Composición

Runtime:

`Campaign Execution Owner Cardinality Hardening → Campaign Coordinate State Decomposition → Campaign Creative Creation Intent Handoff → Campaign Execution Candidate Selector → Campaign Execution Owner Relay → ... → Today`

Browser:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Execution Owner Cardinality Hardening`

Coordinate State Decomposition continúa sin JavaScript propio.

## Seguridad

La capa no añade:

- endpoint de negocio;
- `POST`, `PATCH`, `PUT` o `DELETE`;
- provider read o write;
- IA;
- polling;
- `.click()` sintético;
- `dispatchEvent()`;
- selección por título, similitud, fecha o posición;
- auto-save, auto-ready, auto-publish ni auto-activate.

Action Center conserva identidad, prioridad, rank, urgency, due semantics y orden. Únicamente `EXACT_TARGET` puede mejorar navegación.

## Frozen release boundary

Este hardening vive solo en desarrollo post-W99.

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni autoridad de release/publicación.

La physical UAT real continúa pendiente. No constituye W100, release candidate, Physical-UAT PASS, release authority, publication authority ni production-ready.
