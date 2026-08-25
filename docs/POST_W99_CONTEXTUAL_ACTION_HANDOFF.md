# Post-W99 · Contextual Action Handoff

## Purpose

Contextual Deep Linking ya responde **dónde está el registro exacto**. Contextual Action Handoff responde una pregunta distinta y posterior: **qué control canónico, ya existente en el módulo propietario, corresponde de forma determinística al trabajo que llevó al operador hasta allí**.

La capa no crea una segunda lógica de ejecución. No introduce botones de negocio, endpoints de mutación, reglas de prioridad ni estados de completitud. Observa el contexto efímero de Today/Action Center, espera a que Contextual Deep Linking confirme `FOUND_EXACT` y, solo entonces, describe y resalta un control que el owner ya renderizó.

La secuencia de producto queda:

`Portfolio → Executive Cockpit → Today → Execution Return → Contextual Deep Linking → Evidence Observability → Contextual Action Handoff`

Evidence Observability se conserva como capa anterior y sigue siendo la autoridad para cobertura/frescura de evidencia local; Action Handoff no la reemplaza.

## Source-of-truth boundaries

1. **Action Center** sigue siendo la autoridad de prioridad y motivo.
2. **Contextual Deep Linking** sigue siendo la autoridad de identidad/navegación exacta.
3. **El módulo propietario** sigue siendo la autoridad del control y de cualquier mutación explícita.
4. **Execution Return** sigue siendo el mecanismo para volver al Plan de hoy y releer Action Center después de actuar.
5. **Action Handoff** es únicamente una capa de presentación que une esos cuatro contratos.

La ausencia de un control nunca se interpreta como tarea completada.

## Deterministic mappings

### CRM activity

- Para seguimiento normal/vencido: busca únicamente el botón propietario `Completar` dentro de la actividad exacta.
- Para una prioridad de programación/reprogramación (`crm_unscheduled` o motivo `UNSCHEDULED`): busca únicamente `Reprogramar` dentro del registro exacto.
- Si `Reprogramar` no existe en ese registro, devuelve `CONTROL_NOT_FOUND`; **no usa `Completar` como sustituto**.

### CRM opportunity

Las alertas `PIPELINE_*` describen seguimiento/fecha. La oportunidad visible contiene un selector de etapa, pero cambiar etapa no resuelve esos motivos. Por ello el estado es `NO_ACTION_MAPPING` en lugar de señalar ese selector incorrectamente.

### CRM contact

La tarjeta exacta puede abrir la ficha existente. Se clasifica como `REVIEW_READY / NAVIGATION`, nunca como mutación.

### Publication / Calendar

- `WORKDESK_PUBLICATION_TODAY` se mantiene como revisión manual (`REVIEW_READY`).
- Para estados que sí requieren corrección, la publicación exacta debe estar seleccionada por Editorial y el handoff busca `Guardar nueva versión` en el panel propietario.
- No ejecuta `Cancelar publicación` ni lo promueve como acción por defecto.

### Commercial Desk · lead

Dentro de la fila exacta acepta solamente el control primario ya generado por Mesa Comercial:

- `Vincular · <contacto>`;
- `Resolver conflicto exacto`;
- `Crear contacto`.

Si el conflicto incluye selector, se explicita la selección humana como prerrequisito.

### Commercial Desk · handoff

Busca en el formulario exacto:

- `Crear oportunidad`, o
- `Programar seguimiento`.

El formulario y su POST siguen perteneciendo a Mesa Comercial.

### Campaign

Cuando la campaña exacta está seleccionada y el formulario de campaña está visible, puede señalar `Guardar cambios`. El contrato histórico permanece: poner una campaña `En curso` organiza trabajo y **no** envía mensajes, publica ni activa pauta.

### Campaign Execution

Busca `Ir` dentro de `w64-next`. Es `REVIEW_READY / NAVIGATION`: Execution Workspace dirige al owner del siguiente paso y no ejecuta la mutación.

### Campaign Intelligence

- Para `CAMPAIGN_OPTIONAL_AI`, puede señalar el control propietario `Analizar con IA`; sigue siendo una solicitud opcional/explícita y conserva la confirmación del owner.
- Para el resto, busca `Ir` dentro de `w65-next`, únicamente como navegación al owner canónico.

### Media

Un media exacto puede tener `Usar como Reel` y `Eliminar`, pero ninguno se presupone como respuesta universal a una tarea creativa. `Eliminar` nunca se recomienda por defecto. Sin evidencia adicional, el estado es `NO_ACTION_MAPPING`.

## UX states

- `ACTION_READY`: existe un control exacto y accionable que conserva la mutación en el owner.
- `REVIEW_READY`: existe un control o estado canónico de revisión/navegación, sin afirmar una mutación.
- `CONTROL_NOT_READY`: el control canónico existe pero está deshabilitado en el estado actual.
- `CONTROL_NOT_FOUND`: se esperaba un control determinístico y no está presente; no se sustituye.
- `NO_ACTION_MAPPING`: el registro exacto está localizado, pero ningún control puede asociarse con seguridad al motivo de Action Center.
- `OWNER_ONLY`: no existe un target exacto sobre el cual resolver un control.

El card muestra el modo (`ESCRITURA LOCAL`, `NAVEGACIÓN`, `REVISIÓN`, `IA EXPLÍCITA`) y recuerda que la app **no acciona el control por el operador**.

## Browser contract

`web/contextual-action-handoff.js`:

- captura de forma efímera el item original que llega a `actionCenterOpen`;
- reutiliza `postW99ContextualDeepLinkState` y `contextualDeepLinkFindTarget`;
- espera `FOUND_EXACT`;
- inspecciona exclusivamente el DOM ya renderizado por el owner;
- resalta el control encontrado sin activarlo;
- no usa `opsApi`;
- no usa `fetch`;
- no usa `.click()` sintético;
- no añade polling ni timers de consulta;
- no persiste contexto de negocio;
- limpia el estado al cambiar de empresa.

## Runtime composition

`service_post_w99_contextual_action_handoff_app` hereda `service_post_w99_evidence_observability_integrated_app`.

El handler intercepta únicamente el asset `evidence-observability.js` para agregar después el bootstrap de `contextual-action-handoff.js`. No añade endpoints de negocio. La cadena browser queda:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability → Contextual Action Handoff`.

## Safety contract

- `action_center_priority_authority = true`
- `deep_link_target_authority = true`
- `existing_owner_control_is_authority = true`
- `control_absence_is_not_completion = true`
- `no_synthetic_click = true`
- `no_business_transport = true`
- `no_auto_execution = true`
- `no_provider_reads_writes_by_handoff = true`
- `no_ai_generation_by_handoff = true`
- `no_polling = true`
- `human_execution_required = true`

## Frozen release boundary

Este incremento vive exclusivamente después de W99 en `dev/post-w99-action-center`.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` permanece congelado para la UAT física W99 del issue #113.

No constituye W100, no cambia `v0.9.0`, no reemplaza el candidato físico, no satisface Physical UAT, no concede release/publication authority y no declara production-ready.
