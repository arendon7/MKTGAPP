# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva dos runtimes deliberadamente distintos:

- `binario-marketing serve` → runtime canónico/release existente; no cambia.
- `binario-marketing serve-dev` → entrypoint estable de la cadena post-W99 de desarrollo.

`serve-dev` resuelve `service_post_w99_dev_app`, que actualmente carga Action Center + Pipeline Priority + Global Navigator + Commercial Outcome Intelligence + Decision Review + Portfolio Control Tower + Executive Marketing Cockpit + Today / Operator Execution + Execution Return Flow + Contextual Deep Linking + Evidence Observability + Portfolio Cadence + Contextual Control Handoff + Opportunity Follow-up Control + Existing Activity Reschedule Control + Campaign Results Owner Handoff + Campaign Execution Owner Relay + Campaign Execution Candidate Selector + Campaign Creative Creation Intent Handoff + Campaign Coordinate State Decomposition + Campaign Coordinate Recovery Guidance.

Las superficies superiores son deliberadamente complementarias:

- **Portfolio Control Tower** responde qué empresa requiere atención primero y conserva el orden transversal de Action Center.
- **Executive Marketing Cockpit** responde qué está pasando dentro de la empresa seleccionada en Operación, Comercial, Campañas y Decisiones.
- **Today / Operator Execution** toma como máximo los primeros cinco elementos del Action Center de esa empresa, sin reordenarlos, para convertir la prioridad ya decidida en una secuencia diaria ejecutable.
- **Execution Return Flow** conserva de forma efímera el contexto de navegación cuando una acción se abre desde Today y permite volver al plan después de ejecutar en el módulo propietario. Al regresar relee Today y Action Center; nunca usa el contexto de navegador como estado de completitud.
- **Contextual Deep Linking** usa únicamente los IDs canónicos ya presentes en la acción para enfocar el registro exacto dentro del módulo propietario. Si no existe identidad suficiente o el registro no está presente en la lectura local, abre el owner sin adivinar un sustituto.
- **Evidence Observability** muestra qué evidencia local existe, cuándo fue observada y dónde la cobertura es parcial/no observada/unknown. No consulta proveedores, no califica desempeño y no altera prioridad ni completitud.
- **Portfolio Cadence** describe la semántica temporal de la cola transversal: deadlines ya declarados por la fuente, incidentes, antigüedad observacional de leads, trabajo sin agenda y anomalías temporales. Nunca cambia el orden ni inventa vencimientos.
- **Contextual Control Handoff** toma la acción Today y el target exacto ya resueltos y, solo cuando existe una regla inequívoca, señala el control canónico del owner. No ejecuta el control; si falta, está ambiguo o no corresponde, falla cerrado.
- **Opportunity Follow-up Control** extiende el owner real de oportunidades de Wave 63 con controles separados para `next_action/next_action_at` y nueva actividad CRM. También corrige el deep link de oportunidades para apuntar a `.w63-card` y esperar la carga local de Wave 63. Toda mutación exige submit humano explícito.
- **Existing Activity Reschedule Control** no añade una mutación nueva: integra la reprogramación canónica ya existente de Wave 45. Enruta atención de pipeline al `activity_id` causal exacto cuando es inequívoco y expone `followupRescheduleOpen` dentro de la fila CRM; Wave 45 conserva el único store, endpoint `POST .../reschedule`, validación de fecha futura y timeline.
- **Campaign Results Owner Handoff** cierra el recorrido de resultados por `campaign_id`: añade un GET local read-only para probar identidad exacta incluso antes del primer snapshot, aterriza `CAPTURE_RESULTS / REVIEW_COVERAGE / RECORD_DECISION / REVIEW_RESULTS` en un contexto exacto de campaña dentro de Learning Loop y señala los controles canónicos W52. Para `OPTIONAL_AI`, señala el `Analizar con IA` de W65 en vez del `Ir` genérico. No sustituye refresh, decisiones ni AI owners existentes.
- **Campaign Execution Owner Relay** conserva Wave 64 como autoridad de siguiente acción y resuelve el owner final solo cuando existe un ID canónico único. Cierra `FIX_EXECUTION → publicación`, borrador/programación editorial y `REVIEW_PAID`, repara el target `MEDIA` sobre el Creative Studio W49 real y falla cerrado cuando existen múltiples publicaciones o planes candidatos. No ejecuta ninguna acción final.
- **Campaign Execution Candidate Selector** consume únicamente un `owner_resolution.state = AMBIGUOUS_TARGET` ya proyectado y permite que una persona elija explícitamente uno de los IDs canónicos disponibles. No ordena candidatos, no recomienda, no persiste la elección y no muta negocio. Desde Today elimina la captura genérica provisional de Execution Return y solo la recaptura con el destino exacto después del click humano.
- **Campaign Creative Creation Intent Handoff** trata exclusivamente `CREATE_CREATIVE + OWNER_ONLY`. Conserva `campaign_id` como intención de navegación, pero no inventa un `media_id`: para reutilizar una pieza exige click humano sobre W49; para importar observa únicamente el ID exacto que devuelve el upload canónico y exige un segundo click antes de abrirlo en W49. El selector de campaña y `Guardar ficha creativa` permanecen 100% humanos. `COORDINATE` y Video Studio quedan fuera de ese contrato.
- **Campaign Coordinate State Decomposition** descompone exclusivamente el fallback W64 `COORDINATE` en estados diagnósticos observables (`PUBLICATION_IN_FLIGHT`, distribución cancelada, drift de invariantes o estado no clasificado). Es una capa backend GET-only: adjunta `coordinate_state` a la fila sin cambiar `kind`, `action`, rank, urgencia, orden ni Control Handoff. W64 conserva la autoridad absoluta del siguiente paso.
- **Campaign Coordinate Recovery Guidance** consume únicamente ese diagnóstico residual. Para un único `PUBLISHING` refina navegación al `publication_id` exacto en modo observacional; para distribución totalmente `CANCELLED` usa `CreativeStore.publication_ids / paid_media_ids` como lineage canónica y solo puede aterrizar en un `media_id` exacto W49. Los objetos cancelados siguen terminales, no existe retry automático y cualquier owner/control ambiguo falla cerrado. El adapter browser es zero-transport y jamás dispara los controles que señala.

`service_post_w99_campaign_coordinate_recovery_guidance_app` es ahora el terminal de composición de `serve-dev`. La ascendencia explícita de las capas superiores es:

`service_post_w99_campaign_coordinate_recovery_guidance_app` → `service_post_w99_campaign_coordinate_state_decomposition_app` → `service_post_w99_campaign_creative_creation_intent_handoff_app` → `service_post_w99_campaign_execution_candidate_selector_app` → `service_post_w99_campaign_execution_owner_relay_app` → `service_post_w99_campaign_results_owner_handoff_app` → `service_post_w99_existing_activity_reschedule_control_app` → `service_post_w99_opportunity_followup_control_app` → `service_post_w99_contextual_control_handoff_app` → `service_post_w99_portfolio_cadence_app` → `service_post_w99_evidence_observability_integrated_app` → `service_post_w99_contextual_deep_linking_app` → `service_post_w99_execution_return_app` → Today.

Que una capa deje de ser el terminal directo no elimina su contrato: cada capa posterior hereda la anterior y las pruebas deben verificar esa composición acumulativa, no una posición terminal histórica.

La secuencia de browser bootstraps ahora es:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance`

Campaign Coordinate State Decomposition no aparece en la cadena browser porque sigue siendo backend-only; Recovery Guidance se carga inmediatamente después del adapter de Creative Creation Intent Handoff.

Esto permite seguir construyendo producto mientras `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y su candidato físico W99 permanecen congelados para la UAT del issue #113.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto. Igual que el runtime canónico, rechaza binds no-loopback salvo `--allow-network` explícito.

## Contract

El comando de desarrollo no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, los builders W99 ni el artefacto físico. No debe interpretarse como W100, release candidate ni production-ready.
