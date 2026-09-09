# Post-W99 Portfolio CRM

## Propósito

Portfolio CRM convierte la navegación principal **CRM** en una lectura multiempresa local para el operador que administra varias marcas. La vista reúne únicamente trabajo comercial que ya fue clasificado por módulos canónicos existentes y siempre entrega la ejecución al CRM de la empresa propietaria.

## Autoridades reutilizadas

- **Commercial Pipeline / Wave63** es la autoridad para atención de oportunidades: vencida, sin seguimiento, sin fecha o próxima a vencer.
- **Daily Workdesk / Wave60** es la autoridad temporal para actividades CRM: vencidas, de hoy o sin fecha.
- Portfolio CRM mantiene ambas colas separadas. **No existe un score transversal nuevo** y el valor económico de una oportunidad no altera prioridad.
- El CRM por empresa conserva toda autoridad de mutación: crear/editar contactos, oportunidades, etapas, próximas acciones, actividades o completar seguimientos.

## Minimización

La proyección multiempresa permite sólo contexto necesario para decidir dónde entrar: empresa, IDs internos exactos, título/etapa/valor de la oportunidad, códigos determinísticos de atención, fechas y conteos de seguimiento. No copia teléfonos, emails, direcciones, handles sociales, notas de contacto, notas de oportunidad, cuerpos de actividad ni grafos de identidad.

Las actividades muestran una etiqueta operativa y, cuando existe, el título de la oportunidad vinculada. El texto libre de `activity.summary` permanece únicamente en el CRM propietario.

## Navegación

Entrar a CRM desde la navegación primaria abre **Todas las empresas**. Las tarjetas sólo tienen `Abrir oportunidad` o `Abrir seguimiento`. Ese handoff selecciona la empresa exacta y reutiliza la navegación/contextual deep-link existente; no muta estado comercial por sí mismo. Las acciones provenientes de Hoy/Portfolio que ya apuntan a un CRM concreto conservan el modo de empresa.

## Seguridad

- lectura local únicamente;
- endpoint nuevo sólo `GET /api/portfolio/crm`;
- sin provider reads o provider mutations;
- sin POST/PATCH/DELETE desde la superficie Portfolio CRM;
- sin IA, ejecución automática, polling, timers o almacenamiento de targets en `localStorage`/`sessionStorage`;
- errores locales por empresa se aíslan sin exponer texto de excepción;
- caps explícitos de 200 oportunidades de atención y 200 actividades de atención.

## Bundle de desarrollo

El terminal post-W99 avanza a `service_post_w99_portfolio_crm_app`, conservando `service_post_w99_portfolio_inbox_app` como base acumulativa. El bundle sigue siendo `Binario Marketing IA Post-W99 Dev.app`, sin autoridad de release, Physical UAT ni W100.

La frontera canónica sigue congelada en `main`:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

El repositorio mantiene exactamente tres workflows: `ci.yml`, `full-mac-app.yml` y `persistent-release.yml`.
