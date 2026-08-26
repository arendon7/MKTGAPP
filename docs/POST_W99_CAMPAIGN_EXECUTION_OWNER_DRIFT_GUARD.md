# Post-W99 · Campaign Execution Owner Drift Guard

## Purpose

W64 conserva la autoridad del siguiente trabajo y el Owner Relay solo eleva un target cuando su identidad canónica puede demostrarse. Un `NO_TARGET` bien formado significa algo distinto de una ambigüedad: la operación sigue siendo requerida, pero el objeto concreto esperado ya no está presente en la lectura canónica actual.

Este guard se compone después de Campaign Coordinate Actionability, Campaign Attention Actionability y Setup Readiness Owner Handoff. Primero se estabiliza qué es trabajo real y qué es observación; después se hace visible la deriva solo sobre acciones que siguen en `queue`.

## Estados cubiertos

| source_code | owner | objeto esperado |
| --- | --- | --- |
| `FIX_PUBLICATION` | `calendar` | `PUBLICATION` |
| `SCHEDULE_OR_PUBLISH` | `calendar` | `PUBLICATION` |
| `REVIEW_PAID` | `pauta` | `PAID_DRAFT` |
| `FINISH_CREATIVE` | `content` | `MEDIA` |
| `PREPARE_DISTRIBUTION` | `content` | `MEDIA` |

No convierte `AMBIGUOUS_TARGET`, `EXACT_TARGET` ni `OWNER_ONLY` en drift y no revive filas ya movidas a `observations` por capas anteriores.

## Fail-closed

Solo se anota cuando `state=NO_TARGET`, código/owner coinciden exactamente, `target_id` está vacío, `candidate_count` es entero `0` o texto `"0"`, `candidates=[]`, y existen `campaign_id` y `action_id` no vacíos. Booleanos, floats, cardinalidades residuales, owners/códigos desconocidos y shapes malformados se dejan intactos.

La evidencia aditiva usa `schema=binario.marketing.campaign-execution-owner-drift.v1`, `state=CANONICAL_TARGET_NOT_PRESENT`, `target_selected=false`, `replacement_inferred=false` y `recovery.mode=OPEN_OWNER_AND_REVIEW_CURRENT_STATE` con revisión humana obligatoria.

`queue`, `next_action` y `focus` reciben la misma copia anotada. Orden, rank, urgency, blocking, action, IDs, `owner_resolution` y el array heredado `observations` no cambian. `owner_drift_observations` es solo un índice observacional adicional.

## UX

El browser guard se carga después de `/setup-readiness-owner-handoff.js`. Al abrir una fila con drift válido muestra un aviso y delega al `actionCenterOpen` existente sin reescribir routing. W64 ya declara `calendar`, `pauta` o `content`; el usuario revisa el estado actual en ese owner. Cuando Today/Contextual Control Handoff termina en `TARGET_NOT_EXACT`, una fila con evidencia válida se muestra como `OWNER_STATE_DRIFT / REVISAR OWNER`. Un target exacto siempre prevalece.

## Authority / safety

No hay endpoint de mutación, provider IO, IA, polling, persistencia browser, click/evento sintético, reemplazo inferido, repriorización ni reactivación de observaciones. Setup Readiness conserva sus controles propietarios y toda eventual mutación continúa exigiendo interacción humana explícita en el owner canónico.

## Composición

Runtime:
`Campaign Execution Owner Drift Guard → Setup Readiness Owner Handoff → Campaign Attention Actionability Preservation → Campaign Coordinate Actionability Preservation → Campaign MEDIA Candidate Selection Handoff → ...`

Browser:
`... → Campaign Coordinate Actionability Preservation → Campaign Attention Actionability Preservation → Setup Readiness Owner Handoff → Campaign Execution Owner Drift Guard`

## Frozen release boundary

Solo pertenece a `dev/post-w99-action-center`. `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` / tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` permanece congelado para physical UAT W99 issue #113. No es W100, release candidate, Physical-UAT PASS, publicación ni autorización de `v0.9.0`.
