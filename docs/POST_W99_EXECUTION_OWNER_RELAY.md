# Post-W99 · Execution Owner Relay

## Propósito

Execution Owner Relay cierra la pérdida de identidad que puede ocurrir después de una recomendación de Wave 64. `Execution Workspace` sigue siendo la autoridad que decide **qué tipo de acción viene después**; esta capa únicamente pregunta si los stores canónicos permiten demostrar **qué registro exacto** es el owner final.

Schema local: `binario.marketing.execution-owner-relay.v1`.

El endpoint es:

`GET /api/companies/{company_id}/campaigns/{campaign_id}/execution-owner-context`

Es una proyección local read-only. No consulta Meta, no ejecuta IA, no hace polling y no registra mutaciones.

## Problema que resuelve

Wave 64 conserva correctamente la semántica operacional, pero varias acciones históricas entregan solo `code + view`:

- `FIX_PUBLICATION` → Calendario, sin `publication_id`;
- `SCHEDULE_OR_PUBLISH` → Calendario, sin `publication_id`;
- `REVIEW_PAID` → Pauta, sin `paid_media_id`;
- algunos recorridos creativos incluían un `media_id` derivado del primer elemento disponible.

Ese contrato es suficiente para abrir el módulo, pero no para afirmar que un registro particular es el único owner causal. Execution Owner Relay no modifica Wave 64 ni sustituye sus stores: reconstruye únicamente la identidad desde asociaciones ya persistidas y falla cerrado si hay cero o varios candidatos.

## Contratos

La respuesta declara explícitamente:

- `wave64_is_execution_authority = true`;
- `canonical_stores_are_identity_authority = true`;
- `unique_target_required = true`;
- `no_first_candidate_guessing = true`;
- `navigation_only = true`;
- `business_mutation_authority = false`.

Los estados posibles de `resolution` son:

- `TARGET_RESOLVED`: existe exactamente un registro compatible;
- `TARGET_NOT_AVAILABLE`: no existe un candidato demostrable;
- `TARGET_AMBIGUOUS`: existen varios candidatos y ninguno se elige;
- `OWNER_ONLY`: Wave 64 solo justifica abrir un módulo, no un registro individual.

## Resolución por acción

### FIX_PUBLICATION

Solo puede producir `PUBLICATION` cuando existe exactamente una publicación `FAILED` vinculada canónicamente a la campaña. Dos fallos simultáneos producen `TARGET_AMBIGUOUS`; nunca se usa el primero por posición.

Cuando Results Intelligence originó `FIX_EXECUTION`, el browser exige además que Wave 64 continúe reportando `FIX_PUBLICATION`. Si cambió, se declara contexto envejecido y el relay no continúa.

### SCHEDULE_OR_PUBLISH

Busca únicamente publicaciones `DRAFT` ya vinculadas. Un único borrador permite abrir el panel editorial exacto; cero o varios fallan cerrado.

El panel conserva `Guardar nueva versión` y `Cancelar publicación` como decisiones humanas. El relay no prellena fecha, no guarda y no cancela.

### REVIEW_PAID

Usa `company_paid_media(company_id)` y las asociaciones persistidas de campaña/creativo. Solo un `DRAFT` único puede convertirse en target `PAID_MEDIA`.

En el owner exacto se señala el grupo que contiene `Crear en Meta · PAUSED` y `Cancelar borrador`. El operador conserva la decisión y la confirmación propietaria. La capa no crea Campaign, Ad Set, Creative ni Ad.

### FINISH_CREATIVE

Recalcula los creativos vinculados y considera candidatos únicamente los que aún no están en `READY / SCHEDULED / PUBLISHED / PAID` ni `ARCHIVED`.

Debe existir exactamente uno. El owner exacto es el media de Creative Studio y el control señalado es la ficha que termina en `Guardar ficha creativa`. El operador sigue teniendo que elegir explícitamente el estado correcto —por ejemplo `Lista`—; el relay nunca marca READY por sí mismo.

### PREPARE_DISTRIBUTION

Solo puede elegir un creativo cuando existe exactamente uno en estado efectivo `READY / SCHEDULED / PUBLISHED / PAID`.

El control señalado no es un submit único: es el grupo de decisión que puede incluir `Preparar Facebook`, `Preparar Instagram` y `Enviar a Pauta`. El canal no se preselecciona.

### CREATE_CREATIVE / CALENDAR / COORDINATE

Permanecen `OWNER_ONLY` cuando no existe identidad individual suficiente. Abrir un owner no autoriza a inventar un media, publicación o plan.

## Segundo salto de navegador

La secuencia de presentación es:

`Today → Execution Return → Contextual Deep Linking → ... → Campaign Results Owner Handoff → Execution Owner Relay`

El relay solo aparece cuando la acción Today pertenece al dominio de ejecución y conserva `campaign_id`.

1. relee la acción exacta de Today;
2. hace un único GET local de contexto;
3. compara la acción Today con el `execution_next_action` actual de Wave 64;
4. muestra resolved / unavailable / ambiguous / stale;
5. únicamente un click humano en `Abrir … exacta` instala el contexto del segundo salto;
6. Contextual Deep Linking vuelve a demostrar `FOUND_EXACT`;
7. Contextual Control Handoff puede señalar el control final únicamente si la prueba del relay coincide con el mismo `target_kind + target_id`.

No existen `.click()`, `dispatchEvent`, POST, PATCH, PUT, DELETE ni timers de polling en `execution-owner-relay.js`.

## Owners finales

### PUBLICATION

`editorialState.selectedId` recibe únicamente el ID resuelto y el calendario abre el panel correspondiente.

### MEDIA

Creative Studio conserva `wave49CreativeState.selectedId`. La extensión añade un `data-execution-media-id` transitorio a la card renderizada; no modifica el store.

### PAID_MEDIA

Paid Media Center no tenía selección persistente por draft. La extensión añade un `data-execution-paid-media-id` transitorio al card producido por `wave48PlanSummary`. El ID proviene del row local ya cargado y solo sirve para navegación/énfasis.

Estas marcas DOM no son estado de negocio ni completitud.

## Seguridad y deriva

La capa falla cerrado ante:

- empresa o campaña inexistente/cross-company;
- campaña no representada una sola vez en Execution Workspace;
- varios publication IDs candidatos;
- varios paid draft IDs candidatos;
- varios creativos candidatos;
- cambio entre la acción Today y la acción actual de W64;
- target final que no coincide exactamente con la prueba backend.

La ausencia de un target no significa que la tarea esté completada.

## Frozen release boundary

Execution Owner Relay vive exclusivamente en el trunk post-W99 de desarrollo.

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, el candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni autoridad de release/publicación.

La physical UAT real de W99 continúa pendiente. No constituye W100, release candidate, physical-UAT PASS, release authority, publication authority ni production-ready.
