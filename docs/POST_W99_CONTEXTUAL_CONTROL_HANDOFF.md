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
- `OWNER_CONTROL_GAP`: el registro exacto existe, pero el owner no ofrece un control específico responsable para esa acción.
- `CONTROL_NOT_AVAILABLE`: existe una regla, pero el control esperado no está disponible en el render actual.
- `CONTROL_AMBIGUOUS`: la regla encontró más de un candidato; no elige ninguno.
- `TARGET_NOT_EXACT`: Deep Linking no confirmó un único target exacto.
- `ACTION_CONTEXT_NOT_RESOLVED`: no existe una única acción Today local que corresponda al recorrido.

## Explicit mappings

- `crm_overdue` / `crm_today` + `ACTIVITY` → botón existente `Completar` en CRM. El handoff aclara que señalarlo no obliga a completar; la decisión sigue siendo humana.
- `publication_failed` / `publication_overdue` / `publication_today` + `PUBLICATION` → botón `Gestionar` del calendario editorial.
- `lead_conflict` + `LEAD` → grupo exacto selección de contacto + `Resolver conflicto exacto`.
- `lead_matched` + `LEAD` → botón `Vincular · …` de la coincidencia exacta ya calculada por el owner.
- `lead_new` / `lead_unidentified` + `LEAD` → `Crear contacto`.
- `needs_opportunity` + `HANDOFF` → formulario canónico `Crear oportunidad`.
- `needs_followup` + `HANDOFF` → formulario canónico `Programar seguimiento`.
- `CAMPAIGN_EXECUTION` → botón `Ir` del bloque `w64-next` de la campaña exacta.
- `CAMPAIGN_INTELLIGENCE` → botón `Ir` del bloque `w65-next` de la campaña exacta.

### Intentional owner gap

Las acciones `pipeline_*` sobre `OPPORTUNITY` no se sustituyen por el selector de etapa CRM. Hoy ese selector muta `stage`, mientras varias alertas de pipeline requieren programar o editar seguimiento/próxima acción. La capa declara `OWNER_CONTROL_GAP` hasta que exista un control canónico responsable en el owner.

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

Secuencia de browser bootstraps:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Portfolio Cadence → Contextual Control Handoff`

## Safety

- 0 endpoints de negocio nuevos;
- 0 `opsApi` / `fetch` en el adaptador;
- 0 POST/PATCH/PUT/DELETE;
- 0 provider reads/writes;
- 0 business mutations;
- 0 `.click()` o eventos sintéticos;
- 0 polling/background work;
- 0 IA o fuzzy matching;
- 0 auto-completion;
- 0 nueva autoridad de prioridad.

## Frozen release boundary

Este incremento vive únicamente en el trunk post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, `service.py`, `version.py`, builders, workflows, el candidato físico W99, `v0.9.0`, signing/notarization ni autoridad de release/publicación.

No constituye W100, physical-UAT PASS, release candidate ni production-ready.
