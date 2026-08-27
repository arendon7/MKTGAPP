# Post-W99 · Canonical Change Evidence

## Purpose

Execution Return ya relee Action Center + Today después de que el operador trabaja en el módulo propietario, y Operator Session Progress conserva únicamente el resultado de posición (`STILL_IN_TODAY`, `STILL_PENDING`, `NO_LONGER_PENDING`). **Canonical Change Evidence** añade una capa descriptiva adicional: compara una whitelist estable de la misma fila de Action Center antes de abrirla y después de la relectura.

La finalidad es responder “¿qué cambió en la representación canónica que la app puede observar?” sin afirmar por qué cambió, si la acción fue ejecutada correctamente o si una tarea quedó completada.

## Fuente y momento de la comparación

La capa no consulta endpoints adicionales. Antes de delegar `todayOpen(row)`, toma un snapshot sanitizado de esa misma fila. Cuando `executionReturnBackToToday(context)` termina, reutiliza exclusivamente `postW99ExecutionReturnState.lastResult`, que ya proviene de la relectura canónica Action Center + Today.

Para registrar evidencia deben coincidir exactamente:

1. empresa activa y `context.company_id`;
2. `context.action_id`, `lastResult.action_id` y el `action_id` del snapshot pendiente;
3. `checked_at` no vacío y distinto del valor previo a la relectura;
4. uno de los estados certificados de Execution Return.

Cualquier inconsistencia falla cerrada y no genera un evento.

## Whitelist canónica

El snapshot no serializa la fila completa. Solo captura primitivas de una whitelist fija:

- identidad: `source`, `kind`;
- prioridad observable: `rank`, `urgency`, `blocking`, `due_at`;
- presentación canónica de la fila: `title`, `detail`, `reason.code`;
- destino existente: label, view, tab e IDs `entity/lead/contact/opportunity/campaign/media`;
- owner resolution explícita: state, source code, owner view, target kind, target ID y candidate count;
- `actionability.state` y `owner_drift.state` cuando existen;
- flags exactos `requires_human_action` y `read_only_recommendation`.

Se excluyen deliberadamente `generated_at`, `operator.sequence`, contadores o posiciones de Today, objetos arbitrarios y cualquier dato que no pertenezca a la whitelist. Por eso un cambio de posición del plan no se presenta como cambio del objeto canónico.

## Estados de evidencia

Solo existen tres estados:

### `FIELDS_CHANGED`

La misma `action_id` continúa presente y al menos un campo de la whitelist tiene un valor diferente. El evento conserva únicamente la lista `{field, label, before, after}`. Es evidencia descriptiva y no atribuye causalidad al trabajo del operador.

### `UNCHANGED`

La misma `action_id` continúa presente y todos los campos certificados de la whitelist conservan el mismo valor. No significa que ningún otro dato del módulo propietario haya cambiado.

### `NO_LONGER_PRESENT`

Execution Return produjo `NO_LONGER_PENDING` y `current_action` es nulo. Significa solamente que esa `action_id` no apareció en la nueva cola canónica. **No significa tarea completada**, éxito, resolución ni causalidad.

Si `NO_LONGER_PENDING` llega contradictoriamente con un `current_action`, la evidencia se descarta.

## Persistencia efímera

La capa usa únicamente `sessionStorage` con una clave company-scoped:

`binario.marketing.canonical-change-evidence.v1:<company_id>`

Cada empresa conserva como máximo 20 eventos y un solo snapshot pendiente, coherente con el único recorrido activo de Execution Return. Abrir una nueva acción reemplaza únicamente el snapshot pendiente de esa empresa. Cerrar la pestaña elimina naturalmente la evidencia.

La lectura falla cerrada: eventos desconocidos, cambios fuera de la whitelist, valores no escalares o estados contradictorios se descartan. No se usa `localStorage` ni backend.

## UX

En Hoy, debajo de Operator Session Progress, aparece **Qué cambió en Action Center después de volver** con:

- cantidad de eventos `FIELDS_CHANGED`;
- cantidad `UNCHANGED`;
- cantidad `NO_LONGER_PRESENT`;
- hasta cinco observaciones recientes;
- hasta cuatro diferencias visibles por evento, con `before → after`.

El panel recuerda explícitamente que la evidencia no prueba causalidad, ejecución correcta ni completitud. `Borrar evidencia de cambios` elimina solo la clave local de la empresa activa.

## Authority y safety

Canonical Change Evidence es presentation-only:

- no añade endpoint de negocio;
- no añade POST/PATCH/PUT/DELETE;
- no hace provider reads/writes;
- no llama `fetch`, `opsApi`, XHR ni `sendBeacon`;
- no usa IA;
- no usa polling;
- no dispara click, submit o eventos sintéticos;
- no usa `localStorage`;
- no cambia Action Center, Today, prioridad ni owner resolution;
- no infiere causalidad, éxito o completitud;
- el módulo propietario continúa siendo la única autoridad sobre estado de negocio.

## Composición

Runtime:

`Canonical Change Evidence → Operator Session Progress → Campaign Execution Owner Drift Guard → Setup Readiness Owner Handoff → ...`

Browser tail:

`... → Campaign Execution Owner Drift Guard → Operator Session Progress → Canonical Change Evidence`

El loader se añade al servir `/operator-session-progress.js`; no modifica el comportamiento del parent.

## Frozen release boundary

Este incremento pertenece exclusivamente a `dev/post-w99-action-center`.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` permanecen congelados para la physical UAT W99 del issue #113.

No constituye W100, release candidate, Physical-UAT PASS, publicación, production-ready ni autorización para publicar `v0.9.0`.
