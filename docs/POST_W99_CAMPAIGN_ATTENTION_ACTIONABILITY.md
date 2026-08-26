# Post-W99 · Campaign Attention Actionability Preservation

## Problema

Action Center materializa recomendaciones de campaña como filas humanas con `requires_human_action=true`. Esa normalización es correcta para acciones de ejecución, pero no para tres estados que las fuentes canónicas declaran explícitamente como no requeridos:

- Wave64 `CALENDAR` → `requires_action=false` cuando existe una publicación `QUEUED`.
- Wave65 `REVIEW_RESULTS` → `requires_attention=false` después de existir señal y decisión humana cuando no hay IA configurada.
- Wave65 `OPTIONAL_AI` → `requires_attention=false`; la generación sigue siendo voluntaria y requiere confirmación humana explícita.

`PLANNED_ONLY` y `COORDINATE` ya están cubiertos por capas anteriores. `COMPLETE` no entra a Action Center porque las campañas `COMPLETED/ARCHIVED` se excluyen antes de componer filas.

## Regla exacta

La nueva capa no filtra por `requires_attention=false` de forma global. Wave65 usa ese flag también cuando delega a Wave64 y puede estar heredando acciones que sí requieren ejecución (`DEFINE_CHANNELS`, `CREATE_CREATIVE`, `FINISH_CREATIVE`, `PREPARE_DISTRIBUTION`, `SCHEDULE_OR_PUBLISH`, `REVIEW_PAID`).

Una fila sale de `queue`/Today únicamente cuando existe una lineage 1:1 demostrable:

1. `source=CAMPAIGN`;
2. `kind` es exactamente `calendar`, `review_results` u `optional_ai`;
3. existe `action.campaign_id` no vacío;
4. Results Intelligence contiene exactamente una card de esa campaña;
5. `card.next_action.code` coincide exactamente con `kind`;
6. `card.requires_attention is False`;
7. para `CALENDAR`, además `card.execution.next_action.code == CALENDAR` y `card.execution.requires_action is False`.

Si falta la card, hay duplicados, el código no coincide o el flag no es el booleano exacto `False`, la fila heredada permanece en la cola. La incertidumbre nunca oculta trabajo.

## Proyección

Las filas demostrablemente pasivas pasan de `queue` a `observations` con:

- `requires_human_action=false`;
- `blocking=false`;
- `today_eligible=false`;
- navegación al owner existente permitida;
- lineage explícita `W65_RESULTS_INTELLIGENCE` o `W65_FALLBACK_TO_W64`;
- cero reordenamiento de las acciones restantes.

La capa recalcula `next_action`, `focus`, totales por urgencia/fuente y `campaign_actions`. Conserva sin reinterpretar las métricas ya propiedad de Planned-Only y Coordinate Actionability.

## Autoridad

No cambia Wave64 ni Wave65. Tampoco cambia los handoffs certificados:

- `REVIEW_RESULTS` sigue navegando mediante Campaign Results Owner Handoff.
- `OPTIONAL_AI` sigue usando el control explícito W65; no se genera IA automáticamente.
- `CALENDAR` conserva navegación al calendario/publicación existente.

La diferencia es semántica: una superficie consultable u opcional no ocupa el plan de Hoy si su fuente canónica declara que no requiere atención.

## Runtime y browser

Terminal de desarrollo:

`Campaign Attention Actionability Preservation → Campaign Coordinate Actionability Preservation → Campaign MEDIA Candidate Selection Handoff → Setup Shadow Action Deduplication → Planned-Only Actionability Preservation → ...`

Browser tail:

`... → Campaign MEDIA Candidate Selection Handoff → Campaign Coordinate Actionability Preservation → Campaign Attention Actionability Preservation`

El adapter `campaign-attention-actionability.js` solo renderiza observaciones ya clasificadas por backend y reutiliza `actionCenterOpen` para navegación. No hace `fetch`, XHR, polling, `dispatchEvent`, click sintético, submit ni mutaciones.

## Seguridad

- sin endpoint de negocio nuevo;
- sin provider read/write;
- sin IA automática;
- sin polling;
- sin publicación/retry/paid activation;
- sin mutación de campañas;
- sin repriorización de filas restantes;
- lineage ambigua/incompleta conserva la acción existente.

## Boundary W99

Este incremento vive únicamente en `dev/post-w99-action-center` / `serve-dev`.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` siguen congelados para UAT física real Apple Silicon del issue #113.

No es W100, no prueba Physical-UAT PASS, no concede release/publication authority y no declara production-ready.
