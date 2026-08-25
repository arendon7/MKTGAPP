# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva dos runtimes deliberadamente distintos:

- `binario-marketing serve` → runtime canónico/release existente; no cambia.
- `binario-marketing serve-dev` → entrypoint estable de la cadena post-W99 de desarrollo.

`serve-dev` resuelve `service_post_w99_dev_app`, que actualmente carga Action Center + Pipeline Priority + Global Navigator + Commercial Outcome Intelligence + Decision Review + Portfolio Control Tower + Executive Marketing Cockpit + Today / Operator Execution + Execution Return Flow + Contextual Deep Linking + Evidence Observability + Portfolio Cadence + Contextual Control Handoff + Opportunity Follow-up Control + Existing Activity Reschedule Control + Campaign Results Owner Handoff + Campaign Execution Owner Relay + Campaign Execution Candidate Selector + Campaign Creative Creation Intent Handoff + Campaign Coordinate State Decomposition + Campaign Execution Owner Cardinality Hardening.

## Capas superiores

- **Portfolio Control Tower** responde qué empresa requiere atención primero y conserva el orden transversal de Action Center.
- **Executive Marketing Cockpit** responde qué está pasando dentro de la empresa seleccionada.
- **Today / Operator Execution** presenta hasta los primeros cinco elementos de Action Center sin reordenarlos.
- **Execution Return Flow** conserva contexto efímero de navegación y relee Today/Action Center al volver.
- **Contextual Deep Linking** usa IDs canónicos y falla cerrado cuando no existe identidad suficiente.
- **Evidence Observability** expone evidencia local sin provider refresh, score ni inferencia.
- **Portfolio Cadence** describe semántica temporal sin inventar deadlines ni alterar prioridad.
- **Contextual Control Handoff** señala un control canónico solo bajo reglas inequívocas.
- **Opportunity Follow-up Control** conserva las mutaciones CRM existentes y exige submit humano.
- **Existing Activity Reschedule Control** reutiliza Wave45 como única autoridad de reprogramación.
- **Campaign Results Owner Handoff** cierra resultados por `campaign_id` y conserva Learning Loop/AI como owners.
- **Campaign Execution Owner Relay** conserva Wave64 como autoridad de siguiente acción y resuelve targets finales solo con identidad canónica demostrable.
- **Campaign Execution Candidate Selector** permite selección humana explícita únicamente para ambigüedades `PUBLICATION` y `PAID_DRAFT`; no recomienda ni persiste elección.
- **Campaign Creative Creation Intent Handoff** trata `CREATE_CREATIVE + OWNER_ONLY` sin inventar `media_id`; upload, vínculo de pieza, campaña y guardado siguen siendo humanos.
- **Campaign Coordinate State Decomposition** descompone `COORDINATE` en diagnósticos GET-only sin reescribir `kind`, `action`, rank, urgencia, orden ni Control Handoff.
- **Campaign Execution Owner Cardinality Hardening** impide convertir un `media_id` posicional de Wave64 en identidad final cuando existen varios creativos semánticamente válidos y restaura el invariant de submit canónico único para W49/W35.

## Terminal runtime

`service_post_w99_campaign_execution_owner_cardinality_hardening_app` es ahora el terminal de composición de `serve-dev`.

La ascendencia superior es:

`service_post_w99_campaign_execution_owner_cardinality_hardening_app` →
`service_post_w99_campaign_coordinate_state_decomposition_app` →
`service_post_w99_campaign_creative_creation_intent_handoff_app` →
`service_post_w99_campaign_execution_candidate_selector_app` →
`service_post_w99_campaign_execution_owner_relay_app` →
`service_post_w99_campaign_results_owner_handoff_app` →
`service_post_w99_existing_activity_reschedule_control_app` →
`service_post_w99_opportunity_followup_control_app` →
`service_post_w99_contextual_control_handoff_app` →
`service_post_w99_portfolio_cadence_app` →
`service_post_w99_evidence_observability_integrated_app` →
`service_post_w99_contextual_deep_linking_app` →
`service_post_w99_execution_return_app` → Today.

Que una capa deje de ser el terminal directo no elimina su contrato: las capas posteriores heredan la anterior y la suite verifica composición acumulativa.

## Browser bootstrap

Campaign Coordinate State Decomposition continúa sin JavaScript propio. El browser chain completo y canónico es:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff → Campaign Execution Owner Relay → Campaign Execution Candidate Selector → Campaign Creative Creation Intent Handoff → Campaign Execution Owner Cardinality Hardening`

El prefijo histórico hasta Campaign Creative Creation Intent Handoff se conserva intacto y el hardening se carga únicamente después. No cambia la autoridad de mutación de ninguno de los módulos propietarios.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto. Igual que el runtime canónico, rechaza binds no-loopback salvo `--allow-network` explícito.

## Frozen release boundary

Esto permite seguir construyendo producto mientras `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y su candidato físico W99 permanecen congelados para la UAT del issue #113.

El comando de desarrollo no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, los builders W99 ni el artefacto físico. No debe interpretarse como W100, release candidate ni production-ready.
