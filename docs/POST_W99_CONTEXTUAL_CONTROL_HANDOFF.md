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

Para reglas de `CONTROL_GROUP` que representan una mutación concreta, no basta con que exista un único formulario: el grupo debe contener exactamente un submit canónico y ese submit debe estar habilitado. Un formulario visible con submit ausente, duplicado o deshabilitado no se reporta como `CONTROL_RESOLVED`.

## States

- `CONTROL_RESOLVED`: existe exactamente un control/grupo permitido y se resalta visualmente.
- `OWNER_CONTROL_GAP`: el registro exacto existe, pero el owner no ofrece un control específico responsable para esa acción.
- `CONTROL_NOT_AVAILABLE`: existe una regla, pero el control esperado no está disponible en el render actual.
- `CONTROL_AMBIGUOUS`: la regla encontró más de un candidato; no elige ninguno.
- `TARGET_NOT_EXACT`: Deep Linking no confirmó un único target exacto.
- `ACTION_CONTEXT_NOT_RESOLVED`: no existe una única acción Today local que corresponda al recorrido.

## Explicit base mappings

- `crm_overdue` / `crm_today` + `ACTIVITY` → botón existente `Completar` en CRM. El handoff aclara que señalarlo no obliga a completar; la decisión sigue siendo humana.
- `crm_unscheduled` + `ACTIVITY` → `OWNER_CONTROL_GAP`. El registro exacto abre en CRM, pero la card CRM actual no expone `Reprogramar`; ese control existe en Workdesk/Home. No se cruza implícitamente a otro owner y `Completar` no se usa como sustituto.
- `publication_failed` / `publication_overdue` / `publication_today` + `PUBLICATION` → panel editorial exacto ya abierto por Contextual Deep Linking. Se exige que `editorialState.selectedId` coincida con el `target_id` exacto y que exista un solo `.editorial-panel`; el grupo conserva copy, fecha y elección explícita de guardar o cancelar bajo decisión humana.
- `lead_conflict` + `LEAD` → grupo exacto selección de contacto + `Resolver conflicto exacto`; además debe existir un solo submit canónico habilitado.
- `lead_matched` + `LEAD` → botón `Vincular · …` de la coincidencia exacta ya calculada por el owner.
- `lead_new` / `lead_unidentified` + `LEAD` → `Crear contacto`.
- `needs_opportunity` + `HANDOFF` → formulario canónico `Crear oportunidad`, con submit único y habilitado.
- `needs_followup` + `HANDOFF` → formulario canónico `Programar seguimiento`, con submit único y habilitado.
- `DEFINE_CHANNELS` / `define_channels` + `CAMPAIGN` → formulario de la campaña exacta, solo cuando `campaignState.selectedId === target_id`; requiere un único `Guardar cambios` habilitado. Cambiar el estado de trabajo no envía mensajes, no publica y no activa providers.
- `CAMPAIGN_EXECUTION` → botón `Ir` del bloque `w64-next` de la campaña exacta. Es navegación al siguiente owner, no ejecución de negocio.
- `OPTIONAL_AI` / `optional_ai` + `CAMPAIGN_INTELLIGENCE` → botón propietario `Analizar con IA`, no el botón `Ir`. La solicitud sigue requiriendo la confirmación humana del owner y la IA no ejecuta recomendaciones.

### Semantic disambiguation

El handoff no considera suficiente que un botón exista visualmente. La semántica de `action.kind` debe coincidir con la función real del control:

- `OPTIONAL_AI` no puede resolverse con `Ir`, porque ese botón solo navega y no solicita el análisis IA;
- `crm_unscheduled` no puede resolverse con `Completar`, porque completar no programa una fecha;
- un target `MEDIA` asociado a `CREATE_CREATIVE`, `FINISH_CREATIVE`, `PREPARE_DISTRIBUTION` o `COORDINATE` no puede resolverse genéricamente con `Usar como Reel` ni con `Eliminar`; esos controles son respectivamente específicos de canal o destructivos y no equivalen al objetivo de Action Center;
- el selector de etapa de una oportunidad nunca sustituye seguimiento, próxima acción o actividad CRM.

Cuando la semántica no coincide, el estado correcto es `OWNER_CONTROL_GAP`, no un fallback aproximado.

### Publication exactness

El row de publicación sigue siendo el target que Deep Linking localiza por `publication_id`. Deep Linking también establece `editorialState.selectedId` antes del render, por lo que el owner abre el panel editorial correspondiente. Contextual Control Handoff no vuelve a señalar `Gestionar`: valida la igualdad exacta del ID y señala el panel editorial exacto ya abierto. Si el panel no existe, hay más de uno o el `selectedId` no coincide, la capa falla cerrada.

## Opportunity Follow-up Control extension

Desde PR #128, `Opportunity Follow-up Control` es una extensión posterior que envuelve `controlHandoffResolveControl` únicamente para `target_kind=OPPORTUNITY` y acciones `pipeline_*`. Esto reemplaza el antiguo supuesto de que todas las alertas de pipeline eran necesariamente un owner gap.

La precedencia es deliberada:

1. Opportunity Follow-up Control intenta resolver semánticamente la acción exacta;
2. si puede demostrar un owner control correcto, devuelve ese control;
3. si la alerta corresponde a una actividad existente o no puede atribuirse inequívocamente, devuelve `OWNER_CONTROL_GAP`;
4. solo si la extensión no reconoce la combinación cae al resolver base de Contextual Control Handoff, cuyo fallback sigue siendo fail-closed y nunca usa el selector de etapa como sustituto.

Semántica actual de la extensión:

- `pipeline_overdue_next_action` / `pipeline_unscheduled_next_action` → control de próxima acción de la oportunidad exacta;
- `pipeline_no_followup` → grupo de elección entre próxima acción y nueva actividad, sin preseleccionar una alternativa;
- `pipeline_due_soon` → próxima acción únicamente cuando `due_at` coincide exactamente con `next_action_at` y ninguna actividad pendiente comparte esa fecha;
- `pipeline_overdue_followup` / `pipeline_unscheduled_followup` → `OWNER_CONTROL_GAP`, porque corresponden a una actividad CRM existente y no se crea una actividad sustituta;
- cualquier caso ambiguo permanece fail-closed.

El owner nuevo puede exponer `Gestionar seguimiento`, `Guardar próxima acción` o `Programar seguimiento`. Esos controles pertenecen a `Opportunity Follow-up Control`, no a este adaptador base. Sus mutaciones usan APIs CRM existentes y solo ocurren después de submit humano explícito.

## MEDIA remains fail-closed

Los targets `MEDIA` no promueven `Eliminar` ni `Usar como Reel` como fallback para trabajo creativo/distribución genérico. `Eliminar` es destructivo y `Usar como Reel` es específico de canal; ninguno equivale por defecto a crear/terminar creativo o preparar/coordinar distribución.

Otros targets no mapeados también quedan como `OWNER_CONTROL_GAP`; no hay fuzzy matching por texto, título, fecha o cercanía visual.

## UX contract

El control resuelto recibe únicamente una clase visual y un `data-*` efímero. La capa:

- no registra un listener sobre el control;
- nunca dispara `.click()`;
- no usa `dispatchEvent`;
- no cambia `disabled`, valores, selects, formularios o inputs;
- no hace focus automático;
- no persiste el control;
- no considera el resaltado como completitud.

Execution Return continúa siendo responsable de regresar a Today y releer Action Center después de una ejecución humana real.

## Runtime composition

`service_post_w99_contextual_control_handoff_app` hereda `service_post_w99_portfolio_cadence_app` y solo agrega un asset estático.

El terminal actual añade después `Opportunity Follow-up Control`:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff → Opportunity Follow-up Control`

Este hardening no agrega otra capa terminal ni reemplaza el owner de oportunidad; fortalece el resolver base que esa extensión envuelve.

## Safety

Para `contextual-control-handoff.js`:

- 0 endpoints de negocio nuevos;
- 0 `opsApi` / `fetch`;
- 0 POST/PATCH/PUT/DELETE;
- 0 provider reads/writes;
- 0 business mutations;
- 0 `.click()` o eventos sintéticos;
- 0 polling/background work;
- 0 fuzzy matching;
- IA solo puede señalar el control propietario explícito ya existente; el adaptador no genera IA;
- 0 auto-completion;
- 0 nueva autoridad de prioridad.

Opportunity Follow-up Control conserva por separado sus mutaciones CRM explícitas y humanas; este hardening no añade ni amplía sus endpoints.

## Frozen release boundary

Este incremento vive únicamente en el trunk post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, `service.py`, `version.py`, builders, workflows, el candidato físico W99, `v0.9.0`, signing/notarization ni autoridad de release/publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
