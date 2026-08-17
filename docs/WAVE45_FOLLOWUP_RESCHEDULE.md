# Wave 45 · Follow-up Reschedule

Wave 45 permite reprogramar seguimientos CRM pendientes directamente desde `HOY · PRIORIDADES` sin introducir mensajería ni automatización externa.

## Contrato

- `Reprogramar` abre un editor local de fecha/hora.
- `Guardar fecha` llama exclusivamente a `POST /api/companies/{company_id}/activities/{activity_id}/reschedule`.
- El endpoint acepta únicamente `due_at`.
- La nueva fecha debe ser futura.
- Una actividad ya completada no puede reprogramarse.
- La identidad de actividad, contacto, oportunidad, tipo y resumen permanecen inmutables.
- Cada cambio registra `crm.activity.rescheduled` con `due_from` y `due_to` en timeline.

## Seguridad

Wave 45 no envía WhatsApp, email, mensajes sociales ni respuestas; no llama Meta; no publica ni reintenta publicaciones; no añade polling, timers o trabajo de fondo.

## Gate FULL MAC

El bundle debe lanzar `service_wave45_app`, incluir el store y UI de Wave 45 y superar `audit_wave45_followup_reschedule.sh` en arm64 y x86_64.
