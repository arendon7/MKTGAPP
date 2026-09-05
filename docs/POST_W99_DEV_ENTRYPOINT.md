# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva dos runtimes deliberadamente distintos:

- `binario-marketing serve` → runtime canónico/release existente; no cambia.
- `binario-marketing serve-dev` → entrypoint estable de la cadena post-W99 de desarrollo.

`serve-dev` resuelve `service_post_w99_dev_app` y actualmente carga Action Center + Pipeline Priority + Global Navigator + Commercial Outcome Intelligence + Decision Review + Portfolio Control Tower + Executive Marketing Cockpit + Today / Operator Execution + Execution Return Flow + Contextual Deep Linking + Evidence Observability + Portfolio Cadence + Contextual Control Handoff + Opportunity Follow-up Control + Existing Activity Reschedule Control + Campaign Results Owner Handoff + Campaign Execution Owner Relay + Campaign Execution Candidate Selector + Campaign Creative Creation Intent Handoff + Campaign Coordinate State Decomposition + Campaign Coordinate Recovery Guidance + Campaign Execution Owner Cardinality Hardening + Planned-Only Actionability Preservation + Setup Shadow Action Deduplication + Campaign MEDIA Candidate Selection Handoff + Campaign Coordinate Actionability Preservation + Campaign Attention Actionability Preservation + Setup Readiness Owner Handoff + Campaign Execution Owner Drift Guard + Operator Session Progress + Operator Current Priority Continuity + Operator Return Evidence Delta + Operator Session Evidence Integration.

Las capas superiores son acumulativas. Portfolio/Executive/Today presentan y ordenan trabajo ya canónico; los handoffs posteriores solo refinan navegación, controles o evidencia cuando identidad y cardinalidad pueden demostrarse.

- **Campaign Execution Owner Relay** conserva Wave64 como autoridad y resuelve targets exactos solo con IDs canónicos.
- **Campaign Execution Candidate Selector** permite selección humana explícita para `PUBLICATION` y `PAID_DRAFT` ambiguos, sin ranking ni persistencia.
- **Campaign Creative Creation Intent Handoff** trata `CREATE_CREATIVE + OWNER_ONLY` sin inventar `media_id`.
- **Campaign Coordinate State Decomposition** descompone `COORDINATE` en diagnóstico backend GET-only.
- **Campaign Coordinate Recovery Guidance** convierte solo diagnósticos recuperables en navegación exact-lineage/observacional.
- **Campaign Execution Owner Cardinality Hardening** exige cardinalidad semántica única para `FINISH_CREATIVE/PREPARE_DISTRIBUTION`.
- **Planned-Only Actionability Preservation** conserva `CAMPAIGN/PLANNED_ONLY` como observación fuera de Action Center `queue`/Today.
- **Setup Shadow Action Deduplication** elimina únicamente agregados SETUP con cobertura canónica total demostrable y conserva `shadowed_actions`.
- **Campaign MEDIA Candidate Selection Handoff** mantiene backend `AMBIGUOUS_TARGET` y exige `HUMAN_CLICK` para navegación MEDIA efímera.
- **Campaign Coordinate Actionability Preservation** deja en cola solo `COORDINATE` con `EXACT_RECOVERY_OWNER`; los demás estados son observacionales.
- **Campaign Attention Actionability Preservation** excluye `CALENDAR`, `REVIEW_RESULTS` y `OPTIONAL_AI` solo con lineage única y flags canónicos explícitos de no acción.
- **Setup Readiness Owner Handoff** resuelve readiness SETUP hacia controles propietarios existentes sin clicks/submits/provider IO; `setup_creative` exige click humano real sobre la pieza.
- **Campaign Execution Owner Drift Guard** anota únicamente `NO_TARGET` bien formado sin seleccionar reemplazos ni cambiar prioridad.
- **Operator Session Progress** registra en `sessionStorage` company-scoped únicamente `ACTION_OPENED` y retornos `STILL_IN_TODAY`, `STILL_PENDING`, `NO_LONGER_PENDING`; no es un contador de completadas.
- **Operator Current Priority Continuity** ofrece abrir una prioridad posterior solo cuando el `next_action_id` observado sigue siendo exactamente la prioridad primaria actual; no afirma sucesión causal.
- **Operator Return Evidence Delta** compara un projection whitelist pre-open con la fila ya releída por Execution Return y produce `FIELDS_CHANGED`, `NO_WHITELISTED_CHANGE` o `ACTION_NOT_PRESENT_AFTER_REREAD`, sin completion/causalidad/frescura provider.
- **Operator Session Evidence Integration** integra ese delta ya producido en el `RETURN_OBSERVED` exacto (`company_id + action_id + checked_at`) del historial local. Persiste solo estado, conteo y nombres de campos whitelisted; nunca persiste valores `before/after`, no crea otro evento y confirma el write por reread.

## Terminal de composición

`service_post_w99_operator_session_evidence_integration_app` es el terminal actual de `serve-dev`.

Parents inmediatos retenidos explícitamente para auditabilidad:

- `service_post_w99_operator_return_evidence_delta_app`
- `service_post_w99_operator_current_priority_continuity_app`
- `service_post_w99_operator_session_progress_app`
- `service_post_w99_campaign_execution_owner_drift_guard_app`
- `service_post_w99_setup_readiness_owner_handoff_app`

Ascendencia acumulativa:

`service_post_w99_operator_session_evidence_integration_app` → `service_post_w99_operator_return_evidence_delta_app` → `service_post_w99_operator_current_priority_continuity_app` → `service_post_w99_operator_session_progress_app` → `service_post_w99_campaign_execution_owner_drift_guard_app` → `service_post_w99_setup_readiness_owner_handoff_app` → `service_post_w99_campaign_attention_actionability_app` → `service_post_w99_campaign_coordinate_actionability_app` → `service_post_w99_campaign_media_candidate_selection_handoff_app` → `service_post_w99_setup_shadow_action_deduplication_app` → `service_post_w99_planned_only_actionability_app` → `service_post_w99_campaign_execution_owner_cardinality_hardening_app` → `service_post_w99_campaign_coordinate_recovery_guidance_app` → `service_post_w99_campaign_coordinate_state_decomposition_app` → `service_post_w99_campaign_creative_creation_intent_handoff_app` → `service_post_w99_campaign_execution_candidate_selector_app` → `service_post_w99_campaign_execution_owner_relay_app` → `service_post_w99_campaign_results_owner_handoff_app` → `service_post_w99_existing_activity_reschedule_control_app` → `service_post_w99_opportunity_followup_control_app` → `service_post_w99_contextual_control_handoff_app` → `service_post_w99_portfolio_cadence_app` → `service_post_w99_evidence_observability_integrated_app` → `service_post_w99_contextual_deep_linking_app` → `service_post_w99_execution_return_app` → Today.

## Browser chain

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance → Campaign Execution Owner Cardinality Hardening → Planned-Only Actionability Preservation → Campaign MEDIA Candidate Selection Handoff → Campaign Coordinate Actionability Preservation → Campaign Attention Actionability Preservation → Setup Readiness Owner Handoff → Campaign Execution Owner Drift Guard → Operator Session Progress → Operator Current Priority Continuity → Operator Return Evidence Delta → Operator Session Evidence Integration`

Campaign Coordinate State Decomposition y Setup Shadow Action Deduplication siguen siendo backend-only. Cada adapter browser posterior se carga al final del asset de su parent. Operator Session Evidence Integration se carga al servir `/operator-return-evidence-delta.js`, de modo que el wrapper #152 ya terminó de producir el delta antes de intentar integrarlo en el historial de sesión.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto. Rechaza binds no-loopback salvo `--allow-network` explícito.

## Contract

Esto permite seguir construyendo producto mientras `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` permanecen congelados para la UAT física W99 del issue #113.

El comando de desarrollo no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, builders W99 ni el artefacto físico. No debe interpretarse como W100, Physical-UAT PASS, release candidate ni production-ready.
