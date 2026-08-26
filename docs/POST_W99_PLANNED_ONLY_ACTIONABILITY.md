# Post-W99 · Planned-Only Actionability Preservation

## Propósito

Esta capa corrige una pérdida semántica entre Wave64, Action Center y Today sin crear un sender nuevo ni ampliar autoridad de ejecución.

Wave64 ya define `PLANNED_ONLY` para campañas cuyos canales seleccionados todavía son solo planificables desde el producto actual —por ejemplo `email` o `whatsapp`— y declara explícitamente `requires_action=False`. Wave35 además expone esos canales con `provider_configured=False` y `planned_only=True`.

Antes de esta capa, Action Center reconstruía toda recomendación de campaña mediante `_item()` y asignaba siempre `requires_human_action=True`. Today tomaba después los primeros cinco elementos de esa cola. El resultado era una promoción incorrecta: un estado que Wave64 había declarado no ejecutable podía reaparecer como tarea de operador.

## Regla canónica

Solo se particionan filas que cumplan simultáneamente:

- `source == CAMPAIGN`;
- `kind == planned_only`.

Esas filas:

- salen de `queue`;
- no pueden ser `next_action`;
- salen de `focus.now`, `focus.next` y `focus.later`;
- conservan su identidad, campaña, reason y owner routing dentro de `observations`;
- quedan con `requires_human_action=False`;
- quedan con `actionability.state=NON_ACTIONABLE`;
- quedan con `actionability.today_eligible=False`;
- pueden navegar a la campaña exacta, pero esa navegación no habilita provider ni ejecuta nada.

Todos los demás elementos conservan exactamente su orden heredado. No se recalcula score, rank, urgency, due date, value ni prioridad relativa.

## Por qué no se generaliza a otros códigos W64

`PLANNED_ONLY` es distinto de `CALENDAR`, `REVIEW_RESULTS`, `COORDINATE` u `OPTIONAL_AI`.

Aunque algunos de esos estados no sean `requires_attention` en Wave64/W65, sí representan una revisión, coordinación o acción humana disponible en un owner canónico. `PLANNED_ONLY`, en cambio, expresa que el gate actual no tiene una capacidad de ejecución para ese canal. Por eso esta capa no usa una regla genérica basada en `requires_action=False`.

## Action Center

La proyección conserva `binario.marketing.action-center.v1` y añade de forma compatible:

- `observations`;
- `summary.observations_total`;
- `summary.campaign_observations`;
- contratos explícitos de preservación de actionability.

`queue_total`, urgencias, bloqueantes, `by_source`, `campaign_actions`, `focus` y `next_action` se recomputan únicamente sobre la cola accionable restante.

## Today

No se introduce una segunda regla de selección en Today. `today_execution()` ya llama dinámicamente a `self.action_center()`. Al corregir la semántica del Action Center terminal, Today sigue usando `FIRST_N_CANONICAL_ACTION_CENTER_ITEMS`, pero esos elementos ya no contienen `PLANNED_ONLY`.

Así se preservan simultáneamente:

- Action Center como autoridad de orden;
- máximo cinco acciones en Today;
- ausencia de repriorización;
- exclusión de estados no ejecutables.

## Browser

`planned-only-actionability.js` se carga después de `campaign-execution-owner-cardinality-hardening.js` y añade en Action Center una sección separada **Observaciones · no ejecutables**.

Cada observación puede ofrecer `Ver campaña`, que es solo navegación al owner existente. El adapter no ejecuta `.click()` sintético, no dispara eventos, no persiste selección y no contiene transporte de negocio.

## Composición

Runtime:

`Planned-Only Actionability Preservation → Campaign Execution Owner Cardinality Hardening → Campaign Coordinate Recovery Guidance → Campaign Coordinate State Decomposition → Campaign Creative Creation Intent Handoff → Campaign Execution Candidate Selector → Campaign Execution Owner Relay → … → Today`

Browser:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance → Campaign Execution Owner Cardinality Hardening → Planned-Only Actionability Preservation`

## Seguridad

La capa es local-first y GET-only. No añade endpoint de negocio, `POST/PATCH/PUT/DELETE`, provider read/write, IA, polling, auto-send, auto-publish, auto-activate, auto-save, `.click()` sintético ni `dispatchEvent()`.

No se inventa soporte de email o WhatsApp. Esos canales continúan exactamente bajo el contrato Wave35/W64 existente: planificados, visibles y sin provider ejecutable en este gate.

## Frozen release boundary

No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, candidato físico W99, `service.py`, `version.py`, builders, workflows, tag intent `v0.9.0`, signing/notarization ni autoridad de release/publicación.

La physical UAT real continúa pendiente. No constituye W100, release candidate, Physical-UAT PASS, release authority, publication authority ni production-ready.
