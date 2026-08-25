# Post-W99 · Contextual Control Handoff

## Propósito

Contextual Control Handoff responde, después de que Today y Contextual Deep Linking ya resolvieron una acción y un registro exactos, si el owner actual ofrece un control canónico inequívoco para que el operador continúe.

La capa base es de presentación: no ejecuta el control, no crea una mutación paralela y no elige por similitud. Schema de navegador: `binario.marketing.contextual-control-handoff.v1`.

## Precondiciones fail-closed

Para declarar `CONTROL_RESOLVED` deben cumplirse simultáneamente:

1. existe un contexto activo de Execution Return originado en Today;
2. el mismo `action_id` aparece exactamente una vez en el plan Today local;
3. la empresa activa coincide con ese contexto;
4. Contextual Deep Linking reporta `FOUND_EXACT`;
5. existe exactamente un nodo DOM marcado como target exacto;
6. `action.kind + target_kind` tiene una regla explícita;
7. la regla obtiene exactamente el control o grupo canónico permitido y disponible.

Estados: `CONTROL_RESOLVED`, `OWNER_CONTROL_GAP`, `CONTROL_NOT_AVAILABLE`, `CONTROL_AMBIGUOUS`, `TARGET_NOT_EXACT` y `ACTION_CONTEXT_NOT_RESOLVED`.

## Invariant de CONTROL_GROUP

`controlHandoffSingleGroup` se usa cuando un grupo representa una mutación/formulario con un submit canónico. Exige:

- un solo grupo candidato;
- exactamente un control canónico dentro del grupo;
- el control canónico habilitado.

Cero candidatos produce `CONTROL_NOT_AVAILABLE`; más de uno produce `CONTROL_AMBIGUOUS`; un control `disabled` produce `CONTROL_NOT_AVAILABLE`. Solo el caso único y habilitado puede ser `CONTROL_RESOLVED` y conserva `canonical_node`.

Este invariant cubre actualmente:

- `lead_conflict` → `Resolver conflicto exacto`;
- `needs_opportunity` → `Crear oportunidad`;
- `needs_followup` → `Programar seguimiento`;
- `DEFINE_CHANNELS` → `Guardar cambios` de la campaña exacta;
- editor Wave 45 abierto → `Guardar fecha` de la actividad exacta;
- formulario W52 preparado → `Registrar decisión local` de la campaña exacta.

Un grupo de decisión puede contener más de una alternativa humana por diseño. `Completar o reprogramar seguimiento` es un único contenedor de decisión exacto, no un formulario con submit único.

## Mappings base endurecidos

- `crm_overdue` / `crm_today` + `ACTIVITY`: fallback base `Completar`. Existing Activity Reschedule Control puede asumir ownership terminal y ofrecer ambas decisiones humanas cuando Wave 45 está disponible.
- `crm_unscheduled` + `ACTIVITY`: fallback base `OWNER_CONTROL_GAP`; nunca sustituye `Reprogramar` por `Completar`. Existing Activity Reschedule Control asume ownership cuando puede demostrar la actividad exacta y Wave 45.
- publicación fallida/vencida/de hoy: requiere `editorialState.selectedId === target_id` y un único panel editorial exacto.
- leads y handoffs: solo controles explícitos del owner; no fuzzy matching.
- `define_channels` + `CAMPAIGN`: formulario exacto de campaña + único `Guardar cambios` habilitado.
- `CAMPAIGN_EXECUTION`: `Ir` solo navega al siguiente owner; no ejecuta negocio.
- `optional_ai` + `CAMPAIGN_INTELLIGENCE`: el fallback endurecido usa `Analizar con IA`, nunca el `Ir` genérico. Campaign Results Owner Handoff tiene ownership terminal equivalente sobre W65.
- `CAMPAIGN_INTELLIGENCE` sin control explícito: `OWNER_CONTROL_GAP`.
- `MEDIA` para crear/terminar creativo o preparar/coordinar distribución: `OWNER_CONTROL_GAP`; `Eliminar` y `Usar como Reel` no son sustitutos semánticos.
- `OPPORTUNITY + pipeline_*`: fallback base fail-closed; Opportunity Follow-up Control decide los casos que puede demostrar exactamente.

## Opportunity Follow-up Control

La extensión carga después del handoff base y envuelve `controlHandoffResolveControl` para `OPPORTUNITY + pipeline_*`.

Puede resolver:

- `pipeline_overdue_next_action` / `pipeline_unscheduled_next_action` → próxima acción exacta;
- `pipeline_no_followup` → elección entre próxima acción o nueva actividad, sin preselección;
- `pipeline_due_soon` → próxima acción solo cuando la fuente temporal es inequívoca.

Permanece fail-closed para actividad existente o ambigüedad temporal. Nunca sustituye seguimiento por el selector de etapa.

## Existing Activity Reschedule Control

La extensión siguiente asume únicamente targets `ACTIVITY` demostrados exactamente y reutiliza Wave 45 como única autoridad de reprogramación:

- `CRMStoreWave45.reschedule_activity`;
- `service_wave45_app.AppRuntime.reschedule_activity`;
- `POST /api/companies/{company_id}/activities/{activity_id}/reschedule`;
- `followupRescheduleOpen` / `followup-reschedule.js`.

Semántica:

- `crm_unscheduled` / `pipeline_unscheduled_followup` → `Reprogramar` sobre la actividad exacta;
- si el editor Wave 45 ya está abierto, el handoff exige un único `Guardar fecha` habilitado antes de reportar `CONTROL_RESOLVED`;
- `crm_overdue` / `crm_today` / `pipeline_overdue_followup` / `pipeline_due_soon` derivado inequívocamente de actividad → grupo `Completar o reprogramar seguimiento`;
- actividad ausente, completada, cross-company, Wave 45 ausente o fuente temporal ambigua → fail-closed.

No crea una actividad sustituta, no cambia oportunidad y no duplica el endpoint de Wave 45.

## Campaign Results Owner Handoff

La extensión terminal actual agrega contexto exacto por `campaign_id` y conserva Wave 52 / Wave 65 como autoridades propietarias.

Acciones:

- `capture_results` → `Actualizar resultados desde Meta`; el click humano conserva la confirmación W52 antes de consultar providers.
- `review_coverage` → superficie read-only de campaña exacta.
- `record_decision` → primero `Preparar decisión para esta campaña`; solo después de ese click humano el formulario W52 queda ligado al `campaign_id` exacto. El handoff considera el formulario listo únicamente cuando contiene exactamente un `Registrar decisión local` habilitado. El usuario conserva decisión, rationale y submit final.
- `review_results` → superficie read-only de resultados exactos.
- `optional_ai` → `Analizar con IA` W65, no `Ir`; la confirmación y el contexto sanitizado siguen perteneciendo a W65.

El GET `/api/companies/{company_id}/campaigns/{campaign_id}/results-owner-context` es contexto local read-only. No genera IA ni ejecuta decisiones.

## Composición terminal

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control → Campaign Results Owner Handoff`

Cada extensión envuelve la anterior y conserva su fallback. Action Center sigue siendo autoridad de prioridad; los stores/servicios propietarios siguen siendo autoridad de mutación.

## UX y seguridad

El handoff base:

- nunca dispara `.click()` ni `dispatchEvent`;
- no contiene `opsApi` / `fetch`;
- no registra POST/PATCH/PUT/DELETE;
- no modifica valores, selects, formularios ni `disabled`;
- no hace polling ni background work;
- no hace fuzzy matching ni auto-completion;
- no interpreta resaltado como completitud.

Las extensiones pueden preparar o exponer controles ya certificados, pero las mutaciones ocurren únicamente en el owner y después de una acción humana explícita.

## Frozen release boundary

Este hardening vive únicamente en el trunk post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, el tree W99, `service.py`, `version.py`, builders, workflows, el candidato físico, `v0.9.0`, signing/notarization ni autoridad de release/publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
