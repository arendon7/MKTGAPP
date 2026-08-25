# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva dos runtimes deliberadamente distintos:

- `binario-marketing serve` → runtime canónico/release existente; no cambia.
- `binario-marketing serve-dev` → entrypoint estable de la cadena post-W99 de desarrollo.

`serve-dev` resuelve `service_post_w99_dev_app`, que actualmente carga Action Center + Pipeline Priority + Global Navigator + Commercial Outcome Intelligence + Decision Review + Portfolio Control Tower + Executive Marketing Cockpit + Today / Operator Execution + Execution Return Flow + Contextual Deep Linking + Evidence Observability + Portfolio Cadence + Contextual Control Handoff + Opportunity Follow-up Control + Existing Activity Reschedule Control.

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

`service_post_w99_existing_activity_reschedule_control_app` es ahora el terminal de composición de `serve-dev`. La ascendencia explícita de las capas superiores es:

`service_post_w99_existing_activity_reschedule_control_app` → `service_post_w99_opportunity_followup_control_app` → `service_post_w99_contextual_control_handoff_app` → `service_post_w99_portfolio_cadence_app` → `service_post_w99_evidence_observability_integrated_app` → `service_post_w99_contextual_deep_linking_app` → `service_post_w99_execution_return_app` → Today.

Que una capa deje de ser el terminal directo no elimina su contrato: cada capa posterior hereda la anterior y las pruebas deben verificar esa composición acumulativa, no una posición terminal histórica.

La secuencia de browser bootstraps queda:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control`

Esto permite seguir construyendo producto mientras `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y su candidato físico W99 permanecen congelados para la UAT del issue #113.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto. Igual que el runtime canónico, rechaza binds no-loopback salvo `--allow-network` explícito.

## Contract

El comando de desarrollo no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, los builders W99 ni el artefacto físico. No debe interpretarse como W100, release candidate ni production-ready.
