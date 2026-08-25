# Post-W99 · Opportunity Follow-up Control

## Purpose

Este incremento cierra parte del `OWNER_CONTROL_GAP` que existía para oportunidades del Pipeline Comercial sin introducir un segundo CRM ni una mutación paralela.

El objetivo es que, una vez localizada una oportunidad exacta, el operador pueda abrir un control dentro de la propia card de Wave 63 y decidir explícitamente entre:

1. editar `next_action` / `next_action_at` de la oportunidad; o
2. crear una nueva actividad CRM ligada a esa oportunidad.

Schema de navegador: `binario.marketing.opportunity-followup-control.v1`.

## Integration defect corrected

El Pipeline operativo real de Wave 63 renderiza `.w63-card` dentro de `.w63-board`. Contextual Deep Linking todavía anotaba el pipeline legado `.crm-opportunity`, que Wave 63 elimina del DOM. Por ello un `opportunity_id` canónico podía existir y aun así terminar como `TARGET_NOT_FOUND`.

Esta capa corrige el contrato de composición sin fuzzy matching:

- anota cada `.w63-card` con el `opportunity_id` proveniente de `wave63State.data`;
- respeta exactamente el filtro `wave63State.attentionOnly` para que índice de datos y DOM sigan alineados;
- exige que Wave 63 haya terminado su lectura local antes de considerar listo un target `OPPORTUNITY`;
- vuelve a ejecutar Deep Linking y Control Handoff después de `wave63Draw`, incluido el render asíncrono posterior a `wave63Load`.

No se busca una oportunidad por título, contacto, valor, posición aproximada ni texto visible.

## Owner control

Cada oportunidad abierta de Wave 63 recibe el botón `Gestionar seguimiento`. El botón solo abre/cierra un panel local; no persiste nada.

El panel contiene dos formularios separados.

### Próxima acción

`Guardar próxima acción` usa la API CRM existente:

- método: `PATCH`;
- path: `/api/companies/{company_id}/opportunities/{opportunity_id}`;
- campos escritos: `next_action`, `next_action_at`.

No cambia `stage`, no crea actividad, no envía mensajes y no completa seguimiento.

### Nueva actividad CRM

`Programar seguimiento` usa la API CRM existente:

- método: `POST`;
- path: `/api/companies/{company_id}/activities`;
- referencia canónica: `opportunity_id`;
- campos: `kind`, `summary`, `due_at`.

No envía WhatsApp, email ni llamada; registrar uno de esos tipos solo describe la actividad CRM.

La fecha permanece opcional porque el owner no inventa vencimientos. Si el usuario la omite, cualquier estado `UNSCHEDULED_*` que corresponda puede continuar existiendo.

## Pipeline handoff semantics

La extensión de Contextual Control Handoff es fail-closed y usa `action.kind + opportunity_id` exactos:

- `pipeline_overdue_next_action` → formulario `Editar próxima acción y fecha` cuando el panel está abierto; antes de abrirlo señala `Gestionar seguimiento`.
- `pipeline_unscheduled_next_action` → mismo control de próxima acción.
- `pipeline_no_followup` → grupo completo del panel, porque tanto una próxima acción como una nueva actividad son alternativas canónicas válidas y ninguna debe preseleccionarse.
- `pipeline_due_soon` → formulario de próxima acción **solo** si `due_at` coincide con `next_action_at` y ninguna actividad pendiente tiene exactamente esa misma fecha. Si el origen temporal no es único, falla cerrado.
- `pipeline_overdue_followup` y `pipeline_unscheduled_followup` permanecen `OWNER_CONTROL_GAP`: corresponden a una actividad CRM ya existente y este incremento no crea una actividad sustituta ni modifica silenciosamente la existente.

El selector de etapa jamás se usa como sustituto de seguimiento.

## Refresh semantics

Después de un submit exitoso se releen, en este orden lógico, las fuentes locales propietarias:

- CRM;
- proyección Wave 63;
- Marketing Ops / capas superiores.

El panel vuelve al pipeline de la misma empresa. El cambio de prioridad o desaparición de una alerta depende exclusivamente del nuevo estado canónico releído; el navegador no marca la acción como completada por haber hecho submit.

## Safety

- 0 endpoints de negocio nuevos;
- solo APIs CRM ya existentes;
- 0 provider reads/writes adicionales;
- 0 mensajes automáticos;
- 0 cambio automático de etapa;
- 0 `.click()` o `dispatchEvent` sintéticos;
- 0 polling/background work;
- 0 IA/fuzzy matching;
- 0 fecha inferida;
- 0 auto-completion;
- toda mutación requiere `submit` humano explícito.

## Runtime composition

`service_post_w99_opportunity_followup_control_app` hereda `service_post_w99_contextual_control_handoff_app` y añade únicamente el asset browser `/opportunity-followup-control.js`. Los endpoints PATCH/POST siguen perteneciendo al CRM ya existente.

Secuencia superior de browser bootstraps:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control`

## Frozen release boundary

Este incremento existe solo en el trunk post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, su tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb`, `service.py`, `version.py`, builders, workflows, candidato físico W99, intención de tag `v0.9.0` ni autoridad de publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
