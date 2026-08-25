# Post-W99 · Campaign Execution Candidate Selector

## Propósito

Campaign Execution Owner Relay resuelve un owner final solo cuando existe un único ID canónico. Cuando Wave 64 encuentra más de un objeto válido, conserva `AMBIGUOUS_TARGET` y falla cerrado. Este incremento añade la siguiente pieza mínima: permitir que una persona elija explícitamente uno de esos IDs sin convertir la aplicación en una heurística de selección.

No cambia la prioridad de Action Center, no cambia Wave 64, no persiste una elección y no ejecuta ninguna mutación de negocio.

## Composición

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector`

El terminal `serve-dev` carga el selector después de `campaign-execution-owner-relay.js`.

## Fuente de verdad

El selector no introduce endpoint de negocio ni vuelve a consultar el backend. Consume únicamente la fila ya proyectada por Action Center/Today:

- `owner_resolution.state = AMBIGUOUS_TARGET`
- `owner_resolution.owner_view`
- `owner_resolution.target_kind`
- `owner_resolution.candidate_count`
- `owner_resolution.candidates[]`

La ambigüedad sigue siendo verdad canónica del resolver. La elección humana se representa solo en la copia efímera usada para esa navegación mediante `explicit_owner_selection`.

## Precondiciones fail-closed

Una fila ambigua solo ofrece botones de elección cuando:

1. existe `owner_view`;
2. `target_kind` pertenece al conjunto explícitamente soportado;
3. hay al menos dos candidatos;
4. todos los candidatos tienen ID canónico no vacío;
5. todos los IDs son distintos;
6. `candidate_count` coincide exactamente con la longitud visible.

Si una precondición falla se muestra `Selección bloqueada` y no se abre ningún owner alternativo.

## Target kinds soportados

- `PUBLICATION` → `action.view = calendar`, `action.entity_id = candidate.id`;
- `MEDIA` → `action.view = content`, `action.media_id = candidate.id`;
- `PAID_DRAFT` → `action.view = pauta`, `action.entity_id = candidate.id`;
- `CAMPAIGN` → `action.view = campaigns`, `action.campaign_id = candidate.id`;
- `CAMPAIGN_RESULTS` → `action.view = analytics`, `action.campaign_id = candidate.id`.

El soporte no significa que todos esos tipos deban producir ambigüedad hoy; significa que el adapter no necesita inferir campos si el resolver los produce en el futuro dentro del mismo contrato.

## Semántica de la elección

Los candidatos se muestran en el orden recibido. El selector no ordena por fecha, estado, canal, nombre, valor ni posición. La interfaz declara expresamente que ese orden no representa prioridad ni recomendación.

Solo el evento humano `click` sobre `Elegir este registro` construye una copia de la fila con el ID elegido. La fila original, Action Center y Today permanecen intactos.

La copia añade:

```text
explicit_owner_selection.schema = binario.marketing.campaign-execution-candidate-selector.v1
explicit_owner_selection.source_resolution_state = AMBIGUOUS_TARGET
explicit_owner_selection.selected_by = HUMAN_CLICK
explicit_owner_selection.persisted = false
```

`owner_resolution` no se reescribe: conserva la evidencia de que el backend encontró más de un candidato.

## Execution Return

Existe una interacción específica con Today. Execution Return captura inicialmente la fila antes de que `actionCenterOpen()` llegue al selector. Esa captura contiene el owner genérico W64 y sería incorrecta si el usuario cancela o elige un owner final distinto.

Por eso:

- si el selector se abre desde Today y la captura activa corresponde al mismo `action_id`, la captura provisional se elimina;
- `Cancelar sin abrir` no deja recorrido activo;
- al elegir un candidato se ejecuta `executionReturnCapture(exactItem)` antes de delegar al `actionCenterOpen` previo;
- el mismo `action_id`, posición y prioridad se conservan, pero `destination` ya contiene el owner/ID elegido.

No se crea contexto Execution Return al seleccionar desde Action Center fuera de Today.

## Delegación

Después de una elección válida el selector no implementa navegación propia si existe la cadena canónica: delega al `actionCenterOpen` que ya estaba instalado antes de este adapter. Así se conservan:

- Contextual Deep Linking;
- la reparación W49 de `MEDIA`;
- la identidad W48 de `PAID_DRAFT`;
- Contextual Control Handoff;
- los owners reales W35/W42/W48/W49;
- cualquier regla anterior de retorno y render.

## Cierre por obsolescencia

El selector es efímero. Se cierra sin elegir cuando:

- el usuario pulsa `Cancelar sin abrir`;
- pulsa `Escape`;
- ocurre `marketing-ops-refreshed`;
- la página entra en `pagehide`;
- al elegir, la empresa activa ya no coincide con la empresa con la que se abrió el selector.

Un refresh obliga a volver a abrir la acción desde el estado local recién calculado; no se conserva una lista vieja de candidatos.

## Seguridad

El browser adapter no contiene:

- `opsApi(`;
- `fetch(`;
- `XMLHttpRequest`;
- `.click(`;
- `dispatchEvent(`;
- `setInterval(`;
- `sendBeacon(`;
- métodos POST/PATCH/PUT/DELETE.

La selección no completa tareas, no modifica CRM, no programa/publica, no crea/cancela pauta, no guarda creativos y no modifica campañas. Es únicamente una decisión humana de navegación entre IDs que el backend ya declaró como candidatos canónicos.

## Autoridad

- Action Center conserva prioridad y orden.
- Wave 64 conserva la autoridad del siguiente paso de ejecución.
- Campaign Execution Owner Relay conserva la autoridad para declarar exactitud/ambigüedad.
- El humano conserva la autoridad para desambiguar cuando hay varias opciones.
- El módulo propietario conserva toda autoridad de mutación.

## Boundary W99

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` siguen congelados para Physical UAT issue #113.

Este incremento pertenece exclusivamente a `dev/post-w99-action-center`. No debe interpretarse como W100, Physical UAT PASS, release authority, publication authority ni production-ready.
