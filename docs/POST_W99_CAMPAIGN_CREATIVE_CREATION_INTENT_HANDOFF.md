# Post-W99 · Campaign Creative Creation Intent Handoff

## Purpose

`Campaign Creative Creation Intent Handoff` cierra el gap funcional de `CREATE_CREATIVE` sin inventar un target que todavía no existe.

Campaign Execution Owner Relay ya clasifica `CREATE_CREATIVE` como `OWNER_ONLY`: la campaña necesita crear o vincular una pieza, pero no existe un `media_id` canónico que pueda seleccionarse automáticamente. Esta capa conserva ese límite y transporta únicamente la intención de campaña hasta los controles canónicos de W49.

No crea creativos, no importa archivos por sí sola, no selecciona campañas, no guarda fichas y no llama proveedores.

## Input contract

La capa solo se activa para una fila real de Action Center / Today que cumpla simultáneamente:

- `kind = create_creative`;
- `owner_resolution.state = OWNER_ONLY`;
- `owner_resolution.source_code = CREATE_CREATIVE`;
- `owner_resolution.owner_view = content`;
- `target_kind` vacío;
- `target_id` vacío;
- `candidate_count = 0`;
- `candidates = []`;
- `action.view = content`;
- `action.campaign_id` no vacío.

Cualquier otro `OWNER_ONLY` permanece fuera de este contrato.

En particular, `COORDINATE` **no** se trata como creación. W64 llega a `COORDINATE` cuando ya existe trabajo creativo y el problema es de coordinación/distribución, no de crear o vincular una pieza nueva.

## Browser-only intent

Schema efímero:

`binario.marketing.campaign-creative-creation-intent.v1`

La intención guarda únicamente contexto de navegación:

- `company_id`;
- `action_id`;
- `campaign_id`;
- modo de trabajo elegido por la persona;
- `media_id` solo después de una elección humana exacta;
- origen de esa elección;
- timestamps de interacción;
- `persisted = false`.

No se escribe en stores de negocio ni se añade un endpoint.

## Route A · reutilizar una pieza existente

1. La persona pulsa `Vincular pieza existente`.
2. W49 abre su pipeline canónico.
3. La selección que W49 pueda mostrar por defecto **no cuenta** como elección de la intención.
4. Solo un click humano sobre una `.w49-item` fija el `media_id` de esta guía.
5. La capa verifica que ese `media_id` aparezca exactamente una vez en `wave49CreativeState.context.items`.
6. Verifica además que el formulario visible sea un único `form.w49-form` perteneciente al `selectedId` exacto.
7. Identifica el selector de campaña únicamente porque contiene exactamente una opción cuyo `value` es el `campaign_id` canónico.
8. Resalta ese selector, pero **no cambia `select.value`**.
9. Cuando la persona selecciona manualmente la campaña correcta, resalta el único submit del formulario.
10. `Guardar ficha creativa` continúa siendo el único acto que persiste el vínculo.

No hay matching por título, nombre de archivo, posición visual, similitud o IA.

## Route B · importar una pieza nueva

1. La persona pulsa `Importar archivo`.
2. Se abre la pestaña canónica `Biblioteca / importar`.
3. Se resalta exactamente un `form.company-content-upload`.
4. El upload sigue ocurriendo únicamente mediante el submit humano existente de Wave 34.
5. Esta capa envuelve el helper existente solo para observar su retorno.
6. El store/API canónico de Wave 34 devuelve el registro creado con su `id`; la guía conserva exactamente ese `media_id`.
7. No busca el archivo recién creado por filename, SHA, orden o timestamps.
8. Después del upload **no** navega automáticamente.
9. La persona debe pulsar `Continuar con este archivo`.
10. Solo entonces W49 recibe ese `media_id` exacto como `selectedId`, invalida su cache visual y relee su propio contexto canónico.
11. Desde ahí aplica la misma regla de Route A: elegir campaña manualmente y guardar explícitamente.

## Why Video Studio is outside v1

W49 ofrece `Video Studio`, pero esta iteración no presupone un contrato de retorno exacto entre un render nuevo y el `media_id` final del Creative Studio.

Hasta auditar y certificar esa identidad, la guía no añade navegación especial hacia Video Studio ni intenta recuperar una pieza generada por nombre, orden o proximidad temporal.

El botón nativo de W49 sigue existiendo; simplemente no forma parte de este handoff certificado.

## Fail-closed behavior

La guía no avanza si:

- cambia la empresa activa;
- el `campaign_id` no aparece exactamente una vez en el contexto W49;
- el `media_id` elegido deja de aparecer exactamente una vez;
- el formulario W49 visible no es único;
- no existe exactamente un selector que contenga la opción del `campaign_id`;
- no existe exactamente un submit en ese formulario;
- el formulario de importación no es único.

Nunca elige un sustituto.

## Execution Return

A diferencia de `AMBIGUOUS_TARGET`, `CREATE_CREATIVE` ya navega al owner correcto (`content`) y conserva `campaign_id` en la acción original.

Por eso esta capa **no** borra ni recaptura Execution Return. Today continúa usando el contexto capturado antes de `actionCenterOpen`, y esta guía solo añade contexto efímero dentro del owner.

## Authority split

- W64 conserva la autoridad sobre `CREATE_CREATIVE` como siguiente acción.
- Campaign Execution Owner Relay conserva la verdad `OWNER_ONLY`.
- Esta capa conserva exclusivamente intención de navegación.
- Wave 34 conserva upload y creación de Company Media.
- Wave 49 conserva selección de campaña y PATCH de la ficha creativa.
- Action Center conserva prioridad y orden.
- Execution Return conserva la relectura del plan.

## Safety

El adapter nuevo no contiene:

- `opsApi(`;
- `fetch(`;
- `XMLHttpRequest`;
- `.click(`;
- `dispatchEvent(`;
- `requestSubmit(`;
- `.submit(`;
- `setInterval(`;
- `sendBeacon(`;
- métodos HTTP POST/PATCH/PUT/DELETE propios.

No cambia automáticamente el selector de campaña y no llama `wave49SaveCreative`.

La única observación de una mutación existente es el valor retornado por `contentUpload` después de que el usuario haya enviado el formulario canónico.

## Composition

Browser chain:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff`

`serve-dev` termina en `service_post_w99_campaign_creative_creation_intent_handoff_app`.

Canonical `serve` permanece separado.

## Frozen W99 boundary

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` / tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` continúa congelado para Physical UAT issue #113.

Esta capa no es W100, Physical UAT PASS, release authority, publication authority ni production-ready.
