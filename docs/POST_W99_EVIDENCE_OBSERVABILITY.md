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

`NOT_OBSERVED` significa únicamente que la app no dispone de esa evidencia local. No significa:

- cero impresiones;
- cero clics;
- cero leads;
- cero conversiones;
- mala campaña;
- decisión equivocada;
- estado actual del proveedor.

Un tracking link sigue siendo instrumentación, no evidencia de clic. La atribución conserva `LAST_CAPTURED_TOUCH` y las monedas permanecen separadas.

## Runtime and API

`GET /api/companies/{company_id}/evidence-observability`

`service_post_w99_evidence_observability_app` hereda `service_post_w99_today_execution_app`, conserva Today y toda la cadena anterior, y agrega una superficie GET-only.

El bootstrap se encadena después de `today-execution.js` mediante `evidence-observability.js`.

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

Este incremento vive solo en la rama post-W99 de desarrollo. No modifica `main`, el candidato físico W99, el tag Git ni la cadena de publicación.
