# Post-W99 · Pipeline Priority

## Release boundary

Este incremento continúa únicamente en `dev/post-w99-action-center`, nacida desde el candidato congelado `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`.

- No modifica `main`.
- No reemplaza ni reconstruye el candidato físico W99.
- No crea W100 ni el tag `v0.9.0`.
- La UAT física de W99 y el issue #113 siguen siendo el gate de release independiente.

## Problema de producto

El Pipeline Comercial ya identifica condiciones determinísticas que requieren atención, pero algunas no llegan al Daily Workdesk. El caso más importante es una oportunidad abierta sin siguiente acción o con `next_action_at` vencido aunque no exista una actividad CRM equivalente.

## Integración

Action Center incorpora solamente estas condiciones existentes del Pipeline:

- `OVERDUE_FOLLOWUP`
- `OVERDUE_NEXT_ACTION`
- `NO_FOLLOWUP`
- `UNSCHEDULED_NEXT_ACTION`
- `UNSCHEDULED_FOLLOWUP`
- `DUE_SOON`

Se deduplican contra Workdesk y contra handoffs de Commercial Desk para que un mismo problema no aparezca varias veces.

## Límite analítico

**NO se calcula probabilidad de cierre.** Tampoco se infiere forecast, propensión de compra, churn, lead score o valor esperado.

El valor monetario de la oportunidad puede mostrarse como contexto, pero no modifica `rank`, `urgency` ni el orden de prioridad. La atención proviene únicamente de hechos observables: estado abierto, existencia o ausencia de seguimiento y fechas explícitas.

## Seguridad

La integración sigue siendo una proyección GET/read-only. No genera IA, no consulta providers adicionales, no modifica CRM y no ejecuta recomendaciones automáticamente. El operador siempre navega al módulo canónico (`CRM > Pipeline`) para realizar la acción.
