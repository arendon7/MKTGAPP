# Post-W99 · Campaign Execution Owner Drift Guard

## Purpose

Campaign Execution Owner Relay conserva Wave64 (W64) como autoridad del siguiente trabajo y solo eleva un objeto a target exacto cuando su identidad canónica puede demostrarse. Hay una segunda clase de caso distinta de la ambigüedad: W64 todavía exige una operación, pero el objeto concreto que esa operación esperaba ya no está presente en la lectura canónica actual.

Ejemplos: W64 puede seguir indicando corregir una publicación fallida cuando ya no existe una publicación `FAILED` vinculada; programar/publicar cuando no existe un `DRAFT`; revisar pauta cuando ya no existe un plan `DRAFT`; o terminar/preparar un creativo cuyo `media_id` ya no puede resolverse.

Ese estado no autoriza a escoger otro objeto. **Campaign Execution Owner Drift Guard** hace visible esa deriva y permite abrir el módulo propietario para revisión humana, sin cambiar la autoridad de W64, la prioridad, el objeto de negocio ni el estado persistido.

Este guard se compone después de **Campaign Coordinate Actionability Preservation** y **Campaign Attention Actionability Preservation**. Por tanto, primero se eliminan de `queue`/Today los estados que las fuentes canónicas demuestran como observacionales; solo las acciones que siguen siendo accionables pueden recibir evidencia de drift.

## Estados cubiertos

La capa solo reconoce `owner_resolution.state=NO_TARGET` bien formado para estas combinaciones exactas:

| `source_code` | Owner canónico | Objeto esperado |
| --- | --- | --- |
| `FIX_PUBLICATION` | `calendar` | `PUBLICATION` |
| `SCHEDULE_OR_PUBLISH` | `calendar` | `PUBLICATION` |
| `REVIEW_PAID` | `pauta` | `PAID_DRAFT` |
| `FINISH_CREATIVE` | `content` | `MEDIA` |
| `PREPARE_DISTRIBUTION` | `content` | `MEDIA` |

No convierte `AMBIGUOUS_TARGET`, `EXACT_TARGET` ni `OWNER_ONLY` en drift. En particular, `CALENDAR + OWNER_ONLY` sigue significando que abrir el módulo Calendario es válido aunque no exista una publicación única que deba señalarse; además Campaign Attention Actionability Preservation puede mover ese contexto fuera de la cola cuando W64/W65 demuestran que no requiere acción.

## Contrato fail-closed

Una fila solo recibe `owner_drift` cuando todas estas condiciones son demostrables:

1. `owner_resolution` es un objeto.
2. `state=NO_TARGET` exactamente.
3. `source_code` está en la tabla certificada.
4. `owner_view` coincide exactamente con el owner esperado para ese código.
5. `target_id` está vacío.
6. `candidate_count` es exactamente el entero `0` o el texto `"0"`; booleanos, floats y otros valores se rechazan.
7. `candidates` es una lista vacía.
8. la acción conserva un `campaign_id` no vacío.
9. la fila tiene `action_id` canónico no vacío.

Cualquier incoherencia deja la fila sin anotación. La capa no intenta reparar una resolución malformada.

## Evidencia aditiva

La fila conserva íntegramente `owner_resolution` y recibe únicamente:

```text
owner_drift.schema = binario.marketing.campaign-execution-owner-drift.v1
owner_drift.state = CANONICAL_TARGET_NOT_PRESENT
owner_drift.source_code = <W64 code>
owner_drift.owner_view = <owner>
owner_drift.expected_target_kind = <kind esperado>
owner_drift.campaign_id = <campaign_id canónico>
owner_drift.target_selected = false
owner_drift.replacement_inferred = false
owner_drift.recovery.mode = OPEN_OWNER_AND_REVIEW_CURRENT_STATE
owner_drift.recovery.requires_human_review = true
```

Action Center añade además `owner_drift_observations` como índice observacional de las filas anotadas.

La misma copia anotada se propaga de manera coherente a `queue`, `next_action` y las lanes de `focus`. No se cambia orden, rank, urgency, blocking, label, view ni ningún ID de la acción. El array canónico `observations` heredado de Planned-Only, Coordinate Actionability y Campaign Attention se conserva sin modificación.

## UX

El browser guard se carga después de Campaign Attention Actionability Preservation.

Al abrir una acción con drift válido:

- muestra un aviso breve indicando que el objeto esperado ya no existe en el estado canónico;
- delega al `actionCenterOpen` existente sin reescribir la acción;
- abre el owner que W64 ya había declarado (`calendar`, `pauta` o `content`);
- no selecciona ni sugiere un reemplazo.

Cuando la navegación proviene de Today y Contextual Control Handoff termina en `TARGET_NOT_EXACT`, el guard cambia únicamente la explicación visual a `OWNER_STATE_DRIFT` si la misma action row contiene evidencia `owner_drift` válida. El mensaje solicita revisar el módulo propietario y volver a Hoy. Si Contextual Deep Linking encuentra un target exacto, el guard no lo reemplaza ni lo degrada.

## Authority y safety

La capa no añade autoridad de negocio:

- no añade POST/PATCH/PUT/DELETE;
- no modifica CampaignStore, Social, Creative, Paid Media, CRM ni ningún provider;
- no reescribe `owner_resolution`;
- no elimina filas adicionales de Action Center o Today;
- no revive observaciones excluidas por Coordinate/Attention Actionability;
- no cambia prioridad;
- no selecciona reemplazos;
- no genera IA;
- no usa polling;
- no usa `localStorage` ni `sessionStorage`;
- no dispara clicks o eventos sintéticos;
- toda revisión y eventual mutación sigue ocurriendo en el owner canónico y exige acción humana.

## Composición

Runtime:

`Campaign Execution Owner Drift Guard → Campaign Attention Actionability Preservation → Campaign Coordinate Actionability Preservation → Campaign MEDIA Candidate Selection Handoff → Setup Shadow Action Deduplication → Planned-Only Actionability Preservation → Campaign Execution Owner Cardinality Hardening → ...`

Browser:

`... → Campaign MEDIA Candidate Selection Handoff → Campaign Coordinate Actionability Preservation → Campaign Attention Actionability Preservation → Campaign Execution Owner Drift Guard`

## Frozen release boundary

Este incremento pertenece exclusivamente a `dev/post-w99-action-center`.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y tree `53d1cf04a67da4308b37ac03c0be4546a04f36eb` permanecen congelados para la physical UAT W99 del issue #113.

No constituye W100, release candidate, Physical-UAT PASS, publicación, production-ready ni autorización para publicar `v0.9.0`.
