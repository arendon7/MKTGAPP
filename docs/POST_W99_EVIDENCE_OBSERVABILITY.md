# Post-W99 · Evidence Observability

## Purpose

Evidence Observability responde tres preguntas sin consultar proveedores:

1. ¿qué evidencia existe ya en el estado local canónico?;
2. ¿cuándo fue observada o capturada?;
3. ¿qué cobertura sigue parcial, no observada o sin base suficiente?

No es un dashboard de performance, no puntúa salud de negocio y no sustituye Results Intelligence, Commercial Outcomes ni Decision Review.

## Domains

Schema: `binario.marketing.evidence-observability.v1`.

- `RESULTS_SNAPSHOT`: existencia y timestamp del último snapshot local de resultados.
- `CAMPAIGN_EVIDENCE`: cobertura estructural de señal local por campaña.
- `COMMERCIAL_ATTRIBUTION`: instrumentación, capturas first-party y atribución CRM determinística.
- `DECISION_EVIDENCE`: disponibilidad de evidencia registrada después de decisiones humanas de campaña.

Estados permitidos: `OBSERVED`, `PARTIAL`, `NOT_OBSERVED`, `UNKNOWN`.

## Freshness contract

La app no dispone de una política canónica de expiración para estas evidencias. Por eso:

- conserva `observed_at` cuando existe;
- calcula `age_seconds` solo cuando el timestamp es válido y no está en el futuro;
- clasifica timestamps faltantes, inválidos o futuros explícitamente;
- fija `fresh=null` y `stale=null`;
- declara `policy=NO_STALENESS_THRESHOLD_CONFIGURED`.

La antigüedad es una medición, no un juicio de frescura.

## Absence contract

`NOT_OBSERVED` significa únicamente que la app no dispone de esa evidencia local. No significa cero impresiones, clics, leads o conversiones, ni una mala campaña, una decisión equivocada o el estado actual del proveedor.

Un tracking link sigue siendo instrumentación, no evidencia de clic. La atribución conserva `LAST_CAPTURED_TOUCH` y las monedas permanecen separadas.

## Runtime and API

`GET /api/companies/{company_id}/evidence-observability`

El proyector y sus contratos viven en `service_post_w99_evidence_observability_app`. Ese módulo conserva sus pruebas unitarias y puede evaluarse de forma aislada.

El terminal de `serve-dev` es `service_post_w99_evidence_observability_integrated_app`: hereda `service_post_w99_contextual_deep_linking_app`, reutiliza el mismo proyector y añade únicamente el endpoint GET y el bootstrap de UI.

La composición de navegador queda explícita y acumulativa:

`Today → Execution Return → Contextual Deep Linking → Evidence Observability`.

Evidence Observability se carga después de `contextual-deep-linking.js`; no reemplaza ni intercepta la cadena anterior.

## Safety boundary

- company-scoped;
- local state only;
- read-only projection;
- provider read = false;
- provider mutation = false;
- business mutation = false;
- AI generation = false;
- automatic execution = false;
- background polling = false;
- Action Center priority unchanged;
- Today selection unchanged;
- no business health score;
- no causal inference.

Este incremento vive solo en la rama post-W99 de desarrollo. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, el candidato físico W99, `version.py`, el tag `v0.9.0`, builders, workflows ni la cadena de publicación. No constituye W100 ni production-ready.
