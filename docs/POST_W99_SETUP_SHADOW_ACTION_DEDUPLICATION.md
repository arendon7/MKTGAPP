# Post-W99 · Setup Shadow Action Deduplication

## Purpose

Action Center compone trabajo desde varias proyecciones certificadas. El Command Center aporta prioridades agregadas de preparación (`product_gaps`) y Execution/Results aporta acciones por campaña. Cuando ambos describen exactamente el mismo trabajo, mantener las dos filas en `queue` hace que Today presente una tarea duplicada y degrada la señal operativa.

Esta capa elimina **solo la duplicación demostrable**. No convierte prioridades agregadas en identidad, no infiere cobertura parcial y no altera ninguna acción canónica específica.

## Reglas certificables

### `campaign_media`

El agregado `SETUP/campaign_media` sale de la cola únicamente cuando:

1. existe al menos una campaña activa (`PLANNING`, `READY`, `IN_PROGRESS`) sin `media_ids`;
2. se calcula el conjunto canónico completo de esas campañas desde CampaignStore;
3. cada `campaign_id` de ese conjunto está representado por una acción `CAMPAIGN/create_creative` en Action Center.

Si falta una sola campaña, el agregado permanece accionable.

### `setup_creative`

El readiness `SETUP/setup_creative` se considera shadowed únicamente cuando Creative Studio todavía no tiene ningún perfil guardado **y** ya existe al menos una acción concreta `CAMPAIGN/create_creative`. Esa acción abre el flujo canónico que puede resolver el readiness sin necesidad de repetir una segunda tarea genérica.

Una inconsistencia entre readiness y estado creativo falla cerrada: el SETUP se conserva.

### `paid_draft`

El agregado `SETUP/paid_draft` sale de la cola únicamente cuando todos los IDs canónicos de planes `DRAFT` devueltos por Paid Media están cubiertos por resoluciones `REVIEW_PAID` válidas.

La cobertura solo acepta:

- `source_code=REVIEW_PAID` y `owner_view=pauta`;
- `target_kind=PAID_DRAFT`;
- candidatos estructurados, todos con `status=DRAFT` e IDs no vacíos y únicos;
- `candidate_count` exactamente igual al número real de candidatos;
- `EXACT_TARGET` únicamente con un candidato y `target_id` idéntico a ese ID;
- `AMBIGUOUS_TARGET` únicamente con dos o más candidatos y `target_id` vacío.

Un draft huérfano, una cardinalidad incoherente, un `target_id` contradictorio, un candidato no DRAFT, una forma de candidato inválida o una resolución sin candidatos conserva el agregado.

## Observabilidad

Las filas suprimidas no desaparecen sin rastro. Se copian a `shadowed_actions` con:

- schema `binario.marketing.setup-shadow-action.v1`;
- `state=SUPERSEDED_BY_CANONICAL_ACTIONS`;
- `requires_human_action=false`;
- `today_eligible=false`;
- `reason_code`, explicación y evidencia de cobertura.

`queue`, `next_action`, `focus` y los conteos de `summary` se recalculan exclusivamente con trabajo accionable. Las acciones específicas que hacen la cobertura **nunca** se eliminan.

## Fail-closed

No se deduplican:

- `creative_unprofiled`;
- `creative_campaign`;
- `setup_workspace`;
- `setup_meta`;
- `setup_facebook`;
- `setup_instagram`;
- `setup_ads`;
- `setup_campaign`;
- `setup_crm`;
- ni ningún código futuro no reconocido.

Esto evita sustituir un owner/configuración concreto por una equivalencia no demostrada.

## Authority y safety

La capa es GET/read-only en términos de autoridad de negocio:

- no añade endpoints POST/PATCH/PUT/DELETE;
- no modifica CampaignStore, CreativeStore, PaidMediaStore ni CRM;
- no llama providers;
- no genera IA;
- no hace polling;
- no ejecuta controles;
- no cambia prioridades relativas de las filas que permanecen.

Today hereda el resultado mediante su lectura dinámica de `self.action_center()`: por eso los agregados shadowed dejan de ocupar slots del plan, mientras las acciones canónicas específicas permanecen.

## Frozen release boundary

Este incremento pertenece exclusivamente a `dev/post-w99-action-center`.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` permanecen congelados para la physical UAT de W99 del issue #113.

**No constituye W100**, release candidate, publicación, production-ready ni autorización para publicar `v0.9.0`.
