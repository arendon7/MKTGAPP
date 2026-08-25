# Post-W99 · Existing Activity Reschedule Control

## Purpose

Este incremento completa el owner de seguimientos CRM existentes sin crear actividades sustitutas.

Cuando una actividad pendiente exacta necesita una fecha nueva, el operador puede reprogramar **esa misma actividad**. La única propiedad modificable por este contrato es `due_at`.

Schema de navegador: `binario.marketing.activity-reschedule-control.v1`.

## Narrow mutation contract

Se incorpora una extensión post-W99 de `CRMStore` llamada `PostW99ActivityCRMStore` con una sola operación adicional:

`reschedule_activity(company_id, activity_id, {"due_at": timestamp})`

Reglas:

- `activity_id` debe existir y pertenecer a la empresa exacta;
- la actividad debe seguir pendiente (`completed_at == null`);
- el payload debe ser un objeto;
- `due_at` es obligatorio y debe ser un timestamp válido;
- cualquier campo distinto de `due_at` es rechazado;
- no se puede limpiar la fecha mediante este endpoint;
- una fecha idéntica es idempotente;
- una actividad completada no se puede reprogramar.

No se modifican `company_id`, `contact_id`, `opportunity_id`, `kind`, `summary`, `completed_at` ni `created_at`.

## HTTP owner route

El terminal post-W99 expone únicamente:

`PATCH /api/companies/{company_id}/activities/{activity_id}`

El handler usa el `mutation_lock` existente. No se agrega POST alternativo ni se cambia el endpoint de completar actividad.

Una mutación efectiva agrega al timeline local:

`crm.activity.rescheduled`

con `activity_id`, relaciones canónicas y `due_at_from` / `due_at_to`.

## CRM browser owner

En `Seguimientos`, cada actividad pendiente conserva el botón canónico `Completar` y recibe `Reprogramar`.

`Reprogramar` solo abre un panel local. El cambio ocurre únicamente al submit humano `Guardar nueva fecha`.

Después del submit se releen CRM, Wave 63 y Marketing Ops. La alerta cambia o desaparece solo si las proyecciones canónicas lo determinan a partir del nuevo estado persistido.

## Exact pipeline-to-activity routing

Wave 63 ya expone `followup.next_activity_id`. Este incremento usa ese ID cuando el motivo de atención pertenece inequívocamente a una actividad.

- `pipeline_overdue_followup` → actividad pendiente exacta `next_activity_id`.
- `pipeline_unscheduled_followup` → actividad pendiente exacta `next_activity_id`.
- `pipeline_due_soon` → actividad únicamente si:
  1. `due_at` no coincide con `next_action_at`; y
  2. existe exactamente una actividad pendiente de esa oportunidad con ese `due_at`.

Si `DUE_SOON` puede pertenecer a `next_action_at`, a más de una actividad o a ambas fuentes, el Action Center conserva el owner de oportunidad y el handoff falla cerrado cuando no puede resolver un control inequívoco.

Al resolver una actividad exacta, la acción conserva el mismo `id`, rank, urgency y orden; solo cambia el owner de navegación a:

- `view = crm`
- `tab = followups`
- `entity_id = activity_id`

También se corrige `due_at` de la fila para que corresponda a la actividad causal cuando el código de atención es de seguimiento.

## Handoff semantics

Para target `ACTIVITY`:

- `crm_unscheduled` → `Reprogramar` / formulario de fecha.
- `pipeline_unscheduled_followup` → `Reprogramar` / formulario de fecha.
- `crm_overdue` y `crm_today` → grupo `Completar o reprogramar`.
- `pipeline_overdue_followup` → grupo `Completar o reprogramar`.
- `pipeline_due_soon` cuando fue resuelto a actividad exacta → grupo `Completar o reprogramar`.

No se presupone que una actividad vencida deba completarse: si todavía está pendiente, el operador puede reprogramarla. Tampoco se presupone que deba reprogramarse si realmente ya ocurrió.

## Safety

- mutación local únicamente;
- 0 provider reads/writes;
- 0 mensajes automáticos;
- 0 IA o fuzzy matching;
- 0 creación de actividad sustituta;
- 0 auto-completion;
- 0 cambio de oportunidad o etapa;
- 0 polling/background work;
- 0 `.click()` / `dispatchEvent` sintéticos;
- timestamp obligatorio y explícito;
- actividad completada inmutable para este contrato;
- toda escritura requiere submit humano explícito.

## Runtime composition

`service_post_w99_existing_activity_reschedule_control_app` hereda `service_post_w99_opportunity_followup_control_app` y se convierte en terminal de `serve-dev`.

Secuencia superior:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control`

## Frozen release boundary

Este incremento vive exclusivamente en el trunk post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, candidato físico W99, tag intent `v0.9.0`, builders ni autoridad de publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
