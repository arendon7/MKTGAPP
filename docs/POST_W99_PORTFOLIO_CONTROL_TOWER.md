# Post-W99 · Portfolio Control Tower

## Release boundary

Este incremento vive únicamente en la cadena aislada `dev/post-w99-action-center`, nacida desde el candidato congelado `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`.

- No modifica `main`.
- No reconstruye ni reemplaza el candidato físico W99.
- No crea W100.
- No crea el tag Git `v0.9.0` ni una GitHub Release.
- No altera `service.py`, `version.py`, workflows, builders, signing, notarización ni el gate físico del issue #113.

## Problema de producto

Action Center, Navigator, Commercial Outcomes y Decision Review ya reducen trabajo dentro de una empresa. Sin embargo, un operador con varias empresas todavía debe cambiar manualmente de contexto para descubrir cuál requiere atención primero.

## Solución

`GET /api/portfolio-control-tower` compone una vista multiempresa usando únicamente verdad local ya existente.

Para cada empresa activa reutiliza:

1. **Action Center** como autoridad de prioridad y siguiente acción;
2. **Commercial Outcomes** como contexto exacto de captura, conversión, oportunidades y valores por moneda.

La salida agrega identidad de empresa a cada acción y construye una cola transversal determinística. El operador puede abrir una acción; la UI cambia al contexto de esa empresa mediante el selector existente y después navega al módulo canónico propietario.

## Orden de atención

Portfolio **no crea un health score**. Tampoco pondera el valor económico de una empresa o de una oportunidad.

El orden conserva exactamente los hechos que ya gobiernan Action Center:

- `rank` canónico;
- urgencia `CRITICAL / HIGH / MEDIUM / LOW`;
- condición `blocking`;
- desempates determinísticos por empresa e identidad de acción.

Por lo tanto, una oportunidad de mayor valor nunca salta por encima de una tarea más urgente solo por dinero.

## Economía y monedas

Los valores CRM se muestran únicamente como contexto observado.

- COP se suma con COP;
- USD se suma con USD;
- cualquier otra moneda permanece en su propio bucket;
- no existe conversión FX;
- no existe total monetario cross-currency;
- no se calcula forecast, expected value, propensión de compra o probabilidad de cierre.

## UI

`web/portfolio-control-tower.js` añade el botón **Portfolio** al encabezado de Operaciones. Puede abrirse incluso cuando no hay una empresa seleccionada.

La vista muestra:

- empresas activas y su estado de atención;
- bloqueos y acciones críticas;
- contexto comercial por empresa;
- cola transversal con razón original;
- navegación a la empresa y módulo canónico correspondiente.

Cambiar de empresa desde Portfolio reutiliza `marketingOpsState.selectedCompanyId`, `fillCompanyFilter()` y `refreshMarketingOps()`; no crea una escritura de negocio.

## Safety contract

La torre es estrictamente de lectura:

- estado local solamente;
- GET-only;
- sin provider reads adicionales;
- sin provider writes;
- sin mutaciones CRM/campaña/publicación;
- sin IA;
- sin ejecución automática;
- sin background polling propio;
- sin inferencia causal;
- sin forecast.

La autoridad de ejecución continúa en cada módulo canónico y siempre requiere acción humana.
