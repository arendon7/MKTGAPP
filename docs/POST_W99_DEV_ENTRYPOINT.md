# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva dos runtimes deliberadamente distintos:

- `binario-marketing serve` → runtime canónico/release existente; no cambia.
- `binario-marketing serve-dev` → entrypoint estable de la cadena post-W99 de desarrollo.

`serve-dev` resuelve `service_post_w99_dev_app`, que actualmente carga Action Center + Pipeline Priority + Global Navigator + Commercial Outcome Intelligence + Decision Review + Portfolio Control Tower + Executive Marketing Cockpit + Today / Operator Execution + Execution Return Flow + Contextual Deep Linking + Evidence Observability + Portfolio Cadence + Contextual Control Handoff + Opportunity Follow-up Control + Existing Activity Reschedule Control + Campaign Results Owner Handoff + Campaign Execution Owner Relay + Campaign Execution Candidate Selector + Campaign Creative Creation Intent Handoff + Campaign Coordinate State Decomposition + Campaign Coordinate Recovery Guidance + Campaign Execution Owner Cardinality Hardening.

Las capas superiores son acumulativas y conservan sus autoridades: Portfolio/Executive/Today presentan y ordenan trabajo ya canónico; los handoffs posteriores solo refinan navegación o controles cuando identidad y cardinalidad pueden demostrarse.

- **Campaign Execution Owner Relay** conserva Wave64 como autoridad de siguiente acción y resuelve targets exactos solo con IDs canónicos.
- **Campaign Execution Candidate Selector** permite selección humana explícita para ambigüedades `PUBLICATION` y `PAID_DRAFT` sin recomendación ni persistencia.
- **Campaign Creative Creation Intent Handoff** trata `CREATE_CREATIVE + OWNER_ONLY` sin inventar `media_id`.
- **Campaign Coordinate State Decomposition** descompone el fallback `COORDINATE` en diagnóstico backend GET-only sin reescribir acción o prioridad.
- **Campaign Coordinate Recovery Guidance** convierte únicamente diagnósticos recuperables en navegación exact-lineage/observacional y nunca resucita objetos cancelados ni ejecuta controles.
- **Campaign Execution Owner Cardinality Hardening** exige cardinalidad semántica única para `FINISH_CREATIVE/PREPARE_DISTRIBUTION` antes de elevar `media_id` a `EXACT_TARGET`, y restaura el submit canónico único para W49/W35.

`service_post_w99_campaign_execution_owner_cardinality_hardening_app` es ahora el terminal de composición de `serve-dev`. La ascendencia explícita es:

`service_post_w99_campaign_execution_owner_cardinality_hardening_app` → `service_post_w99_campaign_coordinate_recovery_guidance_app` → `service_post_w99_campaign_coordinate_state_decomposition_app` → `service_post_w99_campaign_creative_creation_intent_handoff_app` → `service_post_w99_campaign_execution_candidate_selector_app` → `service_post_w99_campaign_execution_owner_relay_app` → `service_post_w99_campaign_results_owner_handoff_app` → `service_post_w99_existing_activity_reschedule_control_app` → `service_post_w99_opportunity_followup_control_app` → `service_post_w99_contextual_control_handoff_app` → `service_post_w99_portfolio_cadence_app` → `service_post_w99_evidence_observability_integrated_app` → `service_post_w99_contextual_deep_linking_app` → `service_post_w99_execution_return_app` → Today.

La secuencia browser canónica es:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance → Campaign Execution Owner Cardinality Hardening`

Campaign Coordinate State Decomposition continúa backend-only. Cardinality Hardening se carga inmediatamente después del adapter de Recovery Guidance y delega todos los casos que no sean sus invariants MEDIA/W49/W35.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto. Rechaza binds no-loopback salvo `--allow-network` explícito.

## Contract

Esto permite seguir construyendo producto mientras `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y su candidato físico W99 permanecen congelados para la UAT del issue #113.

El comando de desarrollo no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, los builders W99 ni el artefacto físico. No debe interpretarse como W100, release candidate ni production-ready.
