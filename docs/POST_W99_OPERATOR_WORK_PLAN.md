# Post-W99 · Operator Work Plan

`Operator Work Plan` es una capa read-only de la rama post-W99. No modifica `main` ni el candidato físico W99.

## Propósito

Action Center conserva la autoridad de prioridad. El plan toma su cola exacta y la presenta como una secuencia operativa:

- AHORA: `CRITICAL` y `HIGH`;
- DESPUÉS: `MEDIUM`;
- MÁS TARDE: `LOW`.

No recalcula scores, no reordena y no crea un task manager paralelo. Executive Cockpit aparece solo como contexto y declara `affects_priority_order=false`.

## API

`GET /api/companies/{company_id}/operator-work-plan`

Schema `binario.marketing.operator-work-plan.v1`.

Incluye `first_action`, resumen, brief, secciones, secuencia completa y contexto ejecutivo.

## Contrato

- orden de Action Center preservado;
- sin task store ni ownership inventado;
- sin fechas inventadas: cualquier `due_at` se conserva literalmente;
- sin supuestos de capacidad diaria;
- sin provider reads/writes;
- sin IA;
- sin ejecución automática;
- cada botón abre el módulo canónico propietario.

`service_post_w99_operator_work_plan_app` hereda Portfolio Control Tower + Executive Cockpit y pasa a ser el terminal de `serve-dev`. El runtime canónico `serve` permanece separado.
