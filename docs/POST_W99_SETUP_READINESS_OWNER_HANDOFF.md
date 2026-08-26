# Post-W99 · Setup Readiness Owner Handoff

## Propósito

Action Center conserva algunas filas `SETUP` de Wave50 porque representan readiness todavía incompleta. Después de Setup Shadow Action Deduplication, las filas residuales pueden seguir siendo legítimas, pero su acción original solo abre el módulo (`OWNER_ONLY`) y Contextual Control Handoff no puede señalar qué control resuelve la brecha.

Esta capa cierra ese hueco **sin crear autoridad nueva**: localiza controles canónicos ya renderizados por sus owners y los resalta. No cambia campos, no hace submit, no ejecuta clicks, no consulta providers y no persiste negocio.

## Alcance exacto

Solo aplica a filas Action Center con `source=SETUP` y uno de estos `kind`:

- `setup_workspace`
- `setup_meta`
- `setup_facebook`
- `setup_instagram`
- `setup_ads`
- `setup_campaign`
- `setup_creative`
- `setup_crm`

No intercepta `creative_unprofiled`, `creative_campaign`, `campaign_media`, `paid_draft` ni otras filas SETUP. Esas mantienen sus owners y deduplicaciones existentes.

## Controles propietarios

| Readiness | Owner | Handoff |
| --- | --- | --- |
| `setup_meta` | Empresas & Meta | formulario único `Conectar Meta` |
| `setup_facebook` | Empresas & Meta | campo Página + `Guardar asociaciones` |
| `setup_instagram` | Empresas & Meta | Página con Instagram profesional + `Guardar asociaciones` |
| `setup_ads` | Empresas & Meta | Cuenta publicitaria + `Guardar asociaciones` |
| `setup_workspace` | Video Studio | `Abrir Video Studio` |
| `setup_campaign` | Campañas | formulario único `Crear campaña` |
| `setup_creative` | Creative Studio | flujo humano importar/seleccionar pieza/`Guardar ficha creativa` |
| `setup_crm` | CRM · Contactos | formulario único `Guardar contacto` |

### Prerequisitos Meta

Si Facebook/Instagram/Ads se abre sin credencial Meta, el adapter no intenta asociar activos: señala `Conectar Meta` como prerequisito. Si Meta está conectado pero el selector no contiene activos elegibles, señala `Actualizar activos`. El click humano sobre ese owner puede hacer la lectura remota ya certificada; **el adapter no hace provider IO**.

### `setup_creative` y selección humana

Wave49 puede seleccionar visualmente el primer medio de su pipeline. Esa selección automática **no es aceptada** por este handoff como intención del usuario.

El recorrido es fail-closed:

1. Si no hay medios, señala `+ Importar` y luego el formulario `Agregar a biblioteca`.
2. Si ya hay medios, exige un click humano real sobre `.w49-item`.
3. Solo si el media seleccionado por W49 coincide con ese click humano se señala el formulario único `Guardar ficha creativa`.
4. Nunca asigna `selectedId`, `select.value`, campos de formulario ni ejecuta el submit.

## Estados de presentación

Schema browser-only:

`binario.marketing.setup-readiness-owner-handoff.v1`

Estados relevantes:

- `CONTROL_RESOLVED`
- `PREREQUISITE_CONTROL_RESOLVED`
- `HUMAN_SELECTION_REQUIRED`
- `OWNER_LOADING`
- `STALE_ACTION_CONTEXT`
- `CONTROL_NOT_AVAILABLE`
- `CONTROL_AMBIGUOUS`
- `OWNER_NOT_OPEN`

Cualquier cardinalidad distinta de uno, estado local incompleto o mismatch entre Today y el owner falla cerrado. Una fila stale no se interpreta como completada automáticamente; se pide releer Today.

## Autoridad y seguridad

- Wave50 sigue siendo autoridad de readiness.
- Action Center/Today siguen siendo autoridad de la fila seleccionada.
- Los owners existentes siguen siendo autoridad de formularios, botones, validación y persistencia.
- Esta capa no añade endpoint de negocio.
- No define `do_POST`, `do_PATCH`, `do_PUT` ni `do_DELETE`.
- El JS no usa `fetch`, `XMLHttpRequest`, `opsApi`, `dispatchEvent`, `requestSubmit`, `.click()`, polling ni submit programático.
- Cambiar `crmState.tab` o `wave49CreativeState.tab` solo prepara navegación efímera; no cambia estado de negocio.
- Los providers solo pueden ser consultados por controles propietarios ya existentes y después de interacción humana.

## Composición

`service_post_w99_setup_readiness_owner_handoff_app` hereda de `service_post_w99_campaign_attention_actionability_app`.

Al servir `/campaign-attention-actionability.js`, agrega al final `/setup-readiness-owner-handoff.js`. Así el handoff se ejecuta después de que Campaign Attention Actionability haya estabilizado qué filas realmente permanecen en Action Center/Today.

`serve-dev` apunta a esta capa. `serve` canónico permanece separado.

## Boundary W99

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` continúa congelado para la UAT física W99 del issue #113. Esta capa pertenece únicamente a `dev/post-w99-action-center`.

No es W100, no autoriza `v0.9.0`, no autoriza publicación y no cambia el candidato físico W99.
