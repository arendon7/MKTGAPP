# Post-W99 · Existing Activity Reschedule Control

## Purpose

Este incremento no crea una nueva mutación CRM. Integra en el recorrido post-W99 la capacidad canónica de **reprogramar una actividad existente** que ya fue implementada y certificada en Wave 45.

El problema que resuelve es de ownership y navegación: Action Center podía detectar atención de pipeline causada por una actividad, pero el recorrido Today terminaba en la oportunidad y no siempre en el seguimiento causal exacto. La nueva capa transporta el `activity_id` exacto cuando la fuente es inequívoca y expone dentro de la fila CRM el control Wave 45 ya existente.

Schema del adapter de navegador: `binario.marketing.activity-reschedule-control.v2`.

## Existing authority: Wave 45

La autoridad de escritura permanece en:

- `CRMStoreWave45.reschedule_activity(...)`;
- `service_wave45_app.AppRuntime.reschedule_activity(...)`;
- `POST /api/companies/{company_id}/activities/{activity_id}/reschedule`;
- `web/followup-reschedule.js` y `followupRescheduleOpen(...)`.

Este incremento **no crea un segundo endpoint**, no instala otro CRM store y no redefine `reschedule_activity`.

Wave 45 conserva sus reglas:

- `activity_id` debe existir y pertenecer a la empresa exacta;
- la actividad debe seguir pendiente;
- el payload acepta únicamente `due_at`;
- `due_at` es obligatorio, válido y debe quedar en el futuro;
- una actividad completada no se puede reprogramar;
- solo cambian `due_at` y `updated_at`;
- no se modifican `contact_id`, `opportunity_id`, `kind`, `summary`, `completed_at` ni `created_at`;
- la mutación registra `crm.activity.rescheduled` con `due_from` y `due_to` en el timeline local.

El handler Wave 45 heredado mantiene `mutation_lock`. No existe una ruta PATCH post-W99 para esta operación.

## Browser integration

`product-bootstrap.js` ya carga `/followup-reschedule.js` antes de las capas post-W99. Por ello `activity-reschedule-control.js` es un adapter y no un segundo formulario de negocio.

En `CRM → Seguimientos` el adapter:

1. empareja la fila visible con el `activity_id` canónico de `crmState.activities`;
2. conserva el botón `Completar` existente;
3. añade `Reprogramar` únicamente para actividades pendientes;
4. al click explícito llama `followupRescheduleOpen({entity:'crm_activity', entityId, companyId}, rowNode)`;
5. Wave 45 abre su editor `.followup-reschedule-inline` y mantiene su validación y POST canónicos;
6. tras la actualización de Marketing Ops, si CRM quedó invalidado, el adapter hace únicamente una relectura local y vuelve a renderizar Seguimientos.

El adapter no contiene `opsApi`, no construye payloads de escritura y no puede ejecutar la mutación por sí mismo. Si `followupRescheduleOpen` no está cargado, falla cerrado y no inventa un fallback.

## Exact pipeline-to-activity routing

Wave 63 ya expone `followup.next_activity_id`. La capa post-W99 usa esa identidad cuando la condición del pipeline pertenece inequívocamente a una actividad pendiente.

### Direct activity-derived codes

- `pipeline_overdue_followup` → `followup.next_activity_id` exacto.
- `pipeline_unscheduled_followup` → `followup.next_activity_id` exacto.

El ID solo se acepta si la actividad:

- existe;
- pertenece a la empresa actual;
- pertenece a la oportunidad exacta;
- sigue pendiente.

### `pipeline_due_soon`

`DUE_SOON` puede originarse en `opportunity.next_action_at`, en una actividad o en ambas. Por tanto solo se enruta a `ACTIVITY` cuando:

1. la acción tiene `due_at` explícito;
2. `due_at` **no** coincide con `next_action_at`; y
3. existe exactamente una actividad pendiente de esa oportunidad con ese mismo `due_at`.

Si hay dos actividades con el mismo timestamp, si `next_action_at` comparte el timestamp o si no existe una actividad exacta, la capa no elige por similitud: conserva el owner anterior.

## No reprioritization

Cuando se resuelve una actividad causal, la fila mantiene:

- el mismo `id` estable;
- el mismo `rank`;
- la misma `urgency`;
- la misma posición relativa en la cola.

Solo cambia el destino propietario:

- `view = crm`;
- `tab = followups`;
- `entity_id = activity_id`;
- `label = Abrir seguimiento exacto`.

`owner_resolution` declara `target_kind = ACTIVITY`, `method = EXACT_LOCAL_ID` y `mutation_owner = WAVE45_FOLLOWUP_RESCHEDULE`.

## Contextual Control Handoff

Con un target `ACTIVITY` ya confirmado por Contextual Deep Linking:

- `crm_unscheduled` y `pipeline_unscheduled_followup` → control `Reprogramar` o editor Wave 45 ya abierto;
- `crm_overdue`, `crm_today`, `pipeline_overdue_followup` y un `pipeline_due_soon` resuelto a actividad → grupo humano `Completar o reprogramar seguimiento`.

Esto es deliberado: una actividad vencida no implica que deba marcarse completada. Puede haber ocurrido y requerir `Completar`, o seguir pendiente y requerir `Reprogramar`. El sistema señala ambas decisiones válidas sin tomar ninguna.

## Safety

- una sola autoridad de mutación: Wave 45;
- 0 endpoints de negocio nuevos;
- 0 stores CRM alternativos;
- 0 provider reads/writes;
- 0 mensajes, correos o respuestas automáticas;
- 0 IA, score o fuzzy matching;
- 0 creación de actividad sustituta;
- 0 auto-completion;
- 0 cambio de etapa de oportunidad;
- 0 polling/background work;
- 0 `.click()` o `dispatchEvent()` sintéticos;
- toda escritura sigue exigiendo interacción humana explícita en el editor Wave 45.

## Runtime composition

`service_post_w99_existing_activity_reschedule_control_app` hereda `service_post_w99_opportunity_followup_control_app` y es el terminal de `serve-dev` para este incremento.

La cadena superior queda:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control`

## Frozen release boundary

Este trabajo vive exclusivamente en el trunk post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, candidato físico W99, issue #113, tag intent `v0.9.0`, builders ni autoridad de publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
