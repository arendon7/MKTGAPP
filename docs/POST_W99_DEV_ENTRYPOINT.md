# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva `binario-marketing serve` como runtime canónico/release sin cambios y `binario-marketing serve-dev` como entrypoint estable de la cadena post-W99.

`serve-dev` acumula Action Center, Pipeline Priority, Navigator, Outcomes, Decision Review, Portfolio/Executive/Today, Execution Return, Deep Linking, Evidence, Cadence, Control Handoffs, Campaign Results/Execution, Coordinate Recovery/Cardinality, Planned-Only, Setup Shadow, MEDIA Selection, Coordinate Actionability, Campaign Attention, Setup Readiness Owner Handoff y Campaign Execution Owner Drift Guard.

Las capas superiores conservan sus autoridades. En particular:
- Campaign Coordinate Actionability mueve fuera de `queue` estados COORDINATE no accionables salvo recovery exacto.
- Campaign Attention Actionability excluye solo `CALENDAR`, `REVIEW_RESULTS` y `OPTIONAL_AI` con lineage no-action exacta.
- Setup Readiness Owner Handoff localiza controles SETUP existentes fail-closed sin ejecutar ni persistir intención.
- Campaign Execution Owner Drift Guard corre después de esas capas y solo anota `NO_TARGET` bien formado sobre trabajo que sigue siendo accionable; no selecciona reemplazos ni revive observaciones.

`service_post_w99_campaign_execution_owner_drift_guard_app` es el terminal de `serve-dev` y hereda:

`service_post_w99_campaign_execution_owner_drift_guard_app` → `service_post_w99_setup_readiness_owner_handoff_app` → `service_post_w99_campaign_attention_actionability_app` → `service_post_w99_campaign_coordinate_actionability_app` → `service_post_w99_campaign_media_candidate_selection_handoff_app` → `service_post_w99_setup_shadow_action_deduplication_app` → `service_post_w99_planned_only_actionability_app` → `service_post_w99_campaign_execution_owner_cardinality_hardening_app` → `service_post_w99_campaign_coordinate_recovery_guidance_app` → `service_post_w99_campaign_coordinate_state_decomposition_app` → `service_post_w99_campaign_creative_creation_intent_handoff_app` → `service_post_w99_campaign_execution_candidate_selector_app` → `service_post_w99_campaign_execution_owner_relay_app` → `service_post_w99_campaign_results_owner_handoff_app` → `service_post_w99_existing_activity_reschedule_control_app` → `service_post_w99_opportunity_followup_control_app` → `service_post_w99_contextual_control_handoff_app` → `service_post_w99_portfolio_cadence_app` → `service_post_w99_evidence_observability_integrated_app` → `service_post_w99_contextual_deep_linking_app` → `service_post_w99_execution_return_app` → Today.

Secuencia browser:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Coordinate Recovery Guidance → Campaign Execution Owner Cardinality Hardening → Planned-Only Actionability Preservation → Campaign MEDIA Candidate Selection Handoff → Campaign Coordinate Actionability Preservation → Campaign Attention Actionability Preservation → Setup Readiness Owner Handoff → Campaign Execution Owner Drift Guard`

Campaign Coordinate State Decomposition y Setup Shadow son backend-only. Los adapters browser se cargan acumulativamente; el Drift Guard se añade al servir `/setup-readiness-owner-handoff.js`, por lo que no bypassa Setup Readiness ni los filtros de actionability previos.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto; binds no-loopback requieren `--allow-network`.

## Contract

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y su candidato físico W99 permanecen congelados para UAT issue #113. `serve-dev` no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, builders W99 ni el artefacto físico. No debe interpretarse como W100, release candidate ni production-ready.
