# Post-W99 · Contextual Control Handoff

## Purpose

Contextual Control Handoff responde una pregunta después de que Today y Contextual Deep Linking ya resolvieron una acción y un registro exactos:

> ¿Existe en este owner un control canónico inequívoco que el operador pueda usar para continuar?

La capa es exclusivamente de presentación. Nunca ejecuta el control, nunca crea una mutación paralela y nunca elige por similitud.

Schema de navegador: `binario.marketing.contextual-control-handoff.v1`.

## Preconditions

Para resolver un control deben cumplirse simultáneamente:

1. existe un contexto activo de Execution Return originado en Today;
2. el mismo `action_id` aparece exactamente una vez en el plan Today ya cargado;
3. la empresa activa coincide con el contexto;
4. Contextual Deep Linking reporta `FOUND_EXACT`;
5. existe exactamente un nodo DOM marcado como target exacto;
6. la combinación `action.kind + target_kind` tiene una regla explícita;
7. la regla produce exactamente un control o grupo canónico disponible.

Si cualquiera falla, la capa falla cerrada.

## States

- `CONTROL_RESOLVED`: existe exactamente un control/grupo permitido y se resalta visualmente.
- `OWNER_CONTROL_GAP`: el registro exacto existe, pero el owner no ofrece un control específico responsable para esa acción o la extensión propietaria no puede demostrarlo.
- `CONTROL_NOT_AVAILABLE`: existe una regla, pero el control esperado no está disponible en el render actual.
- `CONTROL_AMBIGUOUS`: la regla encontró más de un candidato; no elige ninguno.
- `TARGET_NOT_EXACT`: Deep Linking no confirmó un único target exacto.
- `ACTION_CONTEXT_NOT_RESOLVED`: no existe una única acción Today local que corresponda al recorrido.

## Base explicit mappings

Contextual Control Handoff conserva reglas base fail-closed. Extensiones posteriores pueden envolver `controlHandoffResolveControl` y asumir ownership únicamente para semánticas que puedan demostrar de forma exacta.

- `crm_overdue` / `crm_today` + `ACTIVITY` → fallback base `Completar`. En el runtime terminal, Existing Activity Reschedule Control tiene precedencia y expone el grupo humano `Completar o reprogramar seguimiento` cuando Wave 45 está disponible.
- `crm_unscheduled` + `ACTIVITY` → fallback base `OWNER_CONTROL_GAP`. El runtime terminal no usa `Completar` como sustituto: Existing Activity Reschedule Control intercepta la actividad exacta y la enlaza al owner Wave 45 de reprogramación.
- `publication_failed` / `publication_overdue` / `publication_today` + `PUBLICATION` → panel editorial exacto ya abierto por Contextual Deep Linking. Se exige que `editorialState.selectedId` coincida con el `target_id` exacto y que exista un solo `.editorial-panel`.
- `lead_conflict` + `LEAD` → grupo exacto selección de contacto + `Resolver conflicto exacto`.
- `lead_matched` + `LEAD` → botón `Vincular · …` de la coincidencia exacta ya calculada por el owner.
- `lead_new` / `lead_unidentified` + `LEAD` → `Crear contacto`.
- `needs_opportunity` + `HANDOFF` → formulario canónico `Crear oportunidad`.
- `needs_followup` + `HANDOFF` → formulario canónico `Programar seguimiento`.
- `DEFINE_CHANNELS` / `define_channels` + `CAMPAIGN` → formulario de la campaña exacta; requiere un único `Guardar cambios` habilitado.
- `CAMPAIGN_EXECUTION` → botón `Ir` del siguiente owner definido por Execution Workspace; navegar no equivale a ejecutar negocio.
- `OPTIONAL_AI` / `optional_ai` + `CAMPAIGN_INTELLIGENCE` → `Analizar con IA`, no el botón genérico `Ir`. El owner conserva confirmación humana y la IA no ejecuta recomendaciones.
- otras acciones de `CAMPAIGN_INTELLIGENCE` sin control específico → `OWNER_CONTROL_GAP`.
- `MEDIA` para `create_creative`, `finish_creative`, `prepare_distribution` o `coordinate` → `OWNER_CONTROL_GAP`; `Eliminar` y `Usar como Reel` no se promueven como sustitutos genéricos.

### Canonical CONTROL_GROUP invariant

Cuando un `CONTROL_GROUP` representa un formulario o una mutación única, `controlHandoffSingleGroup` exige simultáneamente:

1. un solo grupo candidato;
2. exactamente un submit/control canónico dentro del grupo;
3. ese control canónico habilitado.

La ausencia, duplicidad o estado `disabled` devuelve `CONTROL_NOT_AVAILABLE` o `CONTROL_AMBIGUOUS`; nunca `CONTROL_RESOLVED`.

Este invariant se aplica a conflicto de lead, creación de oportunidad, programación de seguimiento, definición de canales y, a través de Existing Activity Reschedule Control, al editor Wave 45 de `Guardar fecha`.

Un grupo de decisión explícita puede contener más de una alternativa humana por diseño. `Completar o reprogramar seguimiento` es un selector de dos decisiones propietarias, no un formulario con submit único, y por eso se valida como un único contenedor de decisión exacto.

## Publication exactness

El row de publicación sigue siendo el target que Deep Linking localiza por `publication_id`. Contextual Deep Linking también establece `editorialState.selectedId` antes del render, por lo que el owner abre el panel editorial correspondiente. Contextual Control Handoff valida la igualdad exacta del ID y señala el panel editorial exacto ya abierto. Si el panel no existe, hay más de uno o el `selectedId` no coincide, la capa falla cerrada.

## Opportunity Follow-up Control extension

Opportunity Follow-up Control carga después del handoff base y envuelve el resolver para `OPPORTUNITY + pipeline_*`.

Resuelve únicamente semánticas demostrables:

- `pipeline_overdue_next_action` / `pipeline_unscheduled_next_action` → próxima acción exacta.
- `pipeline_no_followup` → grupo de elección entre próxima acción o nueva actividad, sin preseleccionar ninguna.
- `pipeline_due_soon` → próxima acción solo cuando `due_at` corresponde inequívocamente a `next_action_at` y ninguna actividad pendiente comparte esa fecha.

Mantiene fail-closed cuando la alerta corresponde a una actividad existente:

- `pipeline_overdue_followup`;
- `pipeline_unscheduled_followup`;
- `pipeline_due_soon` ambiguo.

Esos casos pueden ser re-enrutados posteriormente por Existing Activity Reschedule Control cuando el backend identifica una actividad causal exacta. El selector de etapa nunca sustituye seguimiento.

## Existing Activity Reschedule Control extension

Existing Activity Reschedule Control es la extensión terminal actual para targets `ACTIVITY`. No crea una nueva autoridad de mutación: reutiliza Wave 45.

Autoridad canónica preservada:

- `CRMStoreWave45.reschedule_activity`;
- `service_wave45_app.AppRuntime.reschedule_activity`;
- `POST /api/companies/{company_id}/activities/{activity_id}/reschedule`;
- `web/followup-reschedule.js` / `followupRescheduleOpen`.

Routing exacto:

- `crm_unscheduled` / `pipeline_unscheduled_followup` → botón `Reprogramar` de la actividad exacta; si el editor ya está abierto, el handoff solo resuelve `.followup-reschedule-inline` cuando existe exactamente un `Guardar fecha` habilitado.
- `crm_overdue` / `crm_today` / `pipeline_overdue_followup` / `pipeline_due_soon` derivado de actividad → grupo exacto `Completar o reprogramar seguimiento`.
- una actividad completada, ausente, de otra empresa o sin Wave 45 cargado → fail-closed.
- `pipeline_due_soon` solo se convierte a `ACTIVITY` cuando existe una única actividad pendiente con ese timestamp y `next_action_at` no comparte el mismo `due_at`.

La extensión no crea actividad sustituta, no reescribe summary/kind, no cambia oportunidad, no adivina por texto o proximidad y no desplaza Wave 45 como única autoridad de reprogramación.

## UX contract

El control resuelto recibe únicamente una clase visual y un `data-*` efímero. Contextual Control Handoff:

- no registra un listener de ejecución sobre el control propietario;
- nunca dispara `.click()`;
- no usa `dispatchEvent`;
- no cambia `disabled`, valores, selects, formularios o inputs;
- no hace focus automático;
- no persiste el control;
- no considera el resaltado como completitud.

Las extensiones propietarias pueden exponer controles ya certificados, pero toda mutación continúa ocurriendo únicamente dentro del owner y después de una acción humana explícita.

Execution Return continúa siendo responsable de regresar a Today y releer Action Center después de una ejecución humana real.

## Runtime composition

Secuencia terminal actual:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control → Existing Activity Reschedule Control`

Cada extensión envuelve la anterior y conserva su fallback. No se reemplaza Today, Action Center ni la autoridad de los stores propietarios.

## Safety

Contextual Control Handoff base mantiene:

- 0 endpoints de negocio nuevos;
- 0 `opsApi` / `fetch`;
- 0 POST/PATCH/PUT/DELETE;
- 0 provider reads/writes;
- 0 business mutations;
- 0 `.click()` o eventos sintéticos;
- 0 polling/background work;
- 0 IA o fuzzy matching;
- 0 auto-completion;
- 0 nueva autoridad de prioridad.

Existing Activity Reschedule Control añade solamente routing/UI hacia Wave 45; la escritura sigue perteneciendo al endpoint Wave 45 existente y requiere click/submit humano explícito.

## Frozen release boundary

Este incremento vive únicamente en el trunk post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, `service.py`, `version.py`, builders, workflows, el candidato físico W99, `v0.9.0`, signing/notarization ni autoridad de release/publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
