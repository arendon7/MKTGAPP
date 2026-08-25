# Post-W99 · Commercial Outcome Intelligence

## Goal

Conectar la evidencia comercial first-party ya existente en BINARIO Marketing en una lectura única por campaña:

`campaña → tracking exacto → lead capturado → conversión CRM → oportunidad → estado comercial`.

No es un modelo de atribución probabilística ni un forecast de ventas.

## Truth contract

- Un tracking link representa **instrumentación**, no un clic.
- Un lead cuenta para una campaña únicamente si conserva `tracking_link_id`/`tracking_code` canónico.
- La conversión de lead a contacto u oportunidad sigue siendo explícita y humana.
- El crédito CRM reutiliza `LAST_CAPTURED_TOUCH` del motor canónico de attribution.
- No existe inferencia por cercanía temporal, nombre, email parecido o métricas de proveedor.
- COP, USD y cualquier otra moneda permanecen separadas.
- No se calcula ROAS cuando no existe gasto comparable y trazabilidad suficiente.
- No se calcula probabilidad de cierre.

## Product surface

`GET /api/companies/{company_id}/commercial-outcomes` entrega:

- resumen del embudo first-party;
- campañas con instrumentación, leads y resultado CRM;
- valores atribuidos por moneda;
- journeys mínimos sin PII de contacto;
- siguiente acción comercial determinística;
- contratos y banderas de seguridad.

La UI `commercial-outcomes.js` añade **Resultados comerciales** al runtime `serve-dev`.

## Integration

La lectura se incorpora aditivamente a:

- `results_intelligence_workspace`: mantiene intacto `next_action` de marketing y agrega `commercial_outcome`.
- `marketing_command_center`: mantiene intactas sus prioridades y agrega resumen + atención comercial.

## Safety

La proyección es local, company-scoped y read-only. No hace provider reads, provider writes, mutaciones CRM, generación IA, polling ni ejecución automática.

## Release boundary

Este incremento vive después de W99. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, no cambia el artefacto físico W99 y no debe interpretarse como W100 ni production-ready.
