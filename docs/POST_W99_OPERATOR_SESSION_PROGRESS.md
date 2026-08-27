# Post-W99 · Operator Session Progress

## Purpose

Today / Operator Execution limita el foco a cinco acciones canónicas y Execution Return ya puede releer Action Center después de trabajar en un owner. Hasta este incremento, esa evidencia se mostraba solo para el último regreso y se perdía como contexto operativo al continuar con la siguiente prioridad.

**Operator Session Progress** conserva un historial efímero de la sesión actual para mostrar qué cambios canónicos se observaron mientras el operador ejecuta el plan. No crea tareas, no marca nada como completado y no reemplaza ninguna autoridad de negocio.

## Fuente de verdad

La capa no calcula estados nuevos. Consume únicamente el resultado que `executionReturnBackToToday(context)` ya obtuvo después de releer Action Center + Today.

Solo registra estos estados exactos:

- `STILL_IN_TODAY`: la misma `action_id` sigue dentro del plan diario.
- `STILL_PENDING`: la misma `action_id` sigue en Action Center pero fuera del foco de cinco.
- `NO_LONGER_PENDING`: la misma `action_id` ya no aparece en la cola canónica releída.

`NO_LONGER_PENDING` **no significa tarea completada**. Puede reflejar cualquier cambio canónico que haya retirado esa action ID. El owner correspondiente continúa siendo la única autoridad sobre el estado de negocio.

## Contexto exacto y frescura

Un resultado de regreso solo puede incorporarse al historial cuando:

1. `executionReturnBackToToday` entrega un contexto con `company_id` y `action_id` no vacíos;
2. la empresa activa coincide exactamente con ese `company_id`;
3. `postW99ExecutionReturnState.lastResult.action_id` coincide exactamente con la acción del contexto;
4. `checked_at` existe;
5. el estado pertenece a los tres estados certificados anteriores;
6. el `checked_at` posterior es distinto del `checked_at` que existía antes de invocar la relectura.

La última regla evita reutilizar un resultado viejo si una nueva relectura falla o no produce evidencia fresca. Un regreso fallido no puede transformarse en progreso de sesión a partir de un `lastResult` previo.

Esto impide que un resultado viejo de otra empresa, otra acción o otra relectura contamine la sesión actual.

## Persistencia deliberadamente efímera

El historial usa `sessionStorage`, con una clave company-scoped:

`binario.marketing.operator-session-progress.v1:<company_id>`

Solo contiene contexto de navegación/observación:

- `started_at`;
- snapshot de IDs del plan cuando comienza la sesión;
- eventos `ACTION_OPENED`;
- eventos `RETURN_OBSERVED`;
- posición observada en Today/Action Center;
- siguiente action ID observado, si existe.

Se conservan como máximo 40 eventos. No se usa `localStorage`, no se sincroniza a backend y cerrar la pestaña elimina naturalmente esta memoria de sesión.

La lectura de `sessionStorage` también falla cerrado. Se descartan eventos malformados: todo evento debe tener `action_id`; `ACTION_OPENED` requiere `observed_at`; y `RETURN_OBSERVED` requiere un `checked_at` no vacío y uno de los tres estados certificados. Un estado desconocido nunca cae por defecto en “ya no está en cola”.

## UX

El panel aparece en **Hoy** una vez existe una sesión para la empresa activa. Resume:

- acciones distintas abiertas durante la sesión;
- acciones cuyo último regreso sigue en foco;
- acciones cuyo último regreso sigue pendiente fuera del foco;
- acciones cuyo último regreso ya no aparece en la cola.

La lista muestra hasta cinco observaciones recientes por acción. El texto aclara que “ya no está en cola” es una observación de relectura y no un equivalente de “hecha”.

`Reiniciar registro de sesión` elimina únicamente la clave de `sessionStorage` de la empresa activa. No modifica Action Center, Today, CRM, campañas, publicaciones, contenido, setup ni ningún provider.

## Authority y safety

La capa es presentation-only:

- no añade endpoint de negocio;
- no añade POST/PATCH/PUT/DELETE;
- no usa provider reads/writes;
- no usa IA;
- no usa polling;
- no dispara clicks, submit o eventos sintéticos;
- no escribe `localStorage`;
- no reprioriza Action Center;
- no altera Today;
- no interpreta desaparición de cola como completitud;
- no sustituye Execution Return, que sigue siendo quien realiza la relectura canónica;
- no registra resultados stale ni eventos malformados.

## Composición

Runtime:

`Operator Session Progress → Campaign Execution Owner Drift Guard → Setup Readiness Owner Handoff → Campaign Attention Actionability Preservation → ...`

Browser tail:

`... → Setup Readiness Owner Handoff → Campaign Execution Owner Drift Guard → Operator Session Progress`

El adapter se carga al servir `/campaign-execution-owner-drift-guard.js`. No intercepta ni modifica la semántica de Owner Drift Guard; únicamente envuelve `todayOpen`, `executionReturnBackToToday` y `renderMarketingOps` para conservar contexto efímero y renderizar el panel.

## Frozen W99 boundary

Este incremento pertenece exclusivamente a `dev/post-w99-action-center`.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` permanecen congelados para la physical UAT W99 del issue #113.

No constituye W100, release candidate, Physical-UAT PASS, publicación, production-ready ni autorización para publicar `v0.9.0`.
