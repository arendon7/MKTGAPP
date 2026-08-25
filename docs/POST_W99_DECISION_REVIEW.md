# Post-W99 · Decision Review

## Problema que resuelve

Wave 52 ya permite registrar decisiones humanas (`SCALE`, `ITERATE`, `HOLD`, `RETIRE`) sobre campañas y creativos. Hasta ahora, esas decisiones quedaban persistidas pero no existía una lectura operativa que dijera cuándo aparecía evidencia posterior suficiente para revisarlas.

Decision Review cierra ese loop para decisiones de campaña sin convertir correlación temporal en causalidad.

## Estados

### `AWAITING_EVIDENCE`
La decisión existe, pero no se ha observado después de su `created_at` ninguna de estas condiciones:

- snapshot de marketing con observaciones de esa campaña;
- actualización de una oportunidad CRM acreditada mediante `LAST_CAPTURED_TOUCH`;
- transición posterior de la campaña a estado terminal.

La app no fuerza una nueva decisión y no interpreta la ausencia de evidencia como fracaso.

### `READY_FOR_REVIEW`
Existe evidencia registrada después de la decisión. Esto significa únicamente que ya hay material nuevo para revisión humana.

No significa:

- que la decisión produjo ese resultado;
- que la decisión fue correcta o incorrecta;
- que una venta fue causada por una campaña;
- que deba ejecutarse automáticamente otra acción.

### `FOLLOW_THROUGH_REQUIRED`
Se usa exclusivamente cuando la última decisión humana es `RETIRE` y la campaña continúa en un estado no terminal.

El motivo es contractual: una `LearningDecision` nunca ejecuta cambios de campaña. El sistema solo recuerda que existe una decisión humana que todavía no se refleja en un estado terminal y dirige a la superficie de campañas para que una persona decida qué hacer.

## Evidencia posterior

### Marketing observado
Se considera únicamente un `LearningSnapshot` posterior a la decisión cuyo rollup para esa campaña tenga `evidence=OBSERVED`.

### CRM atribuido
Se reconstruye el crédito canónico `LAST_CAPTURED_TOUCH` por oportunidad. Solo cuenta como evidencia posterior cuando el touch acreditado o la actualización del registro CRM ocurre después de la decisión.

Los valores permanecen separados por moneda. No se calcula ROAS si no existe una base comparable y no se genera forecast.

### Estado de campaña
Una transición posterior a `COMPLETED` o `ARCHIVED` puede abrir revisión del ciclo, pero no se interpreta como resultado comercial.

## Integración

Decision Review se incorpora de forma aditiva en:

- `Results Intelligence`: cada campaña con decisión recibe `decision_review` sin reemplazar `next_action` existente;
- `Marketing Command Center`: agrega resumen y hasta cinco elementos de atención;
- `Action Center`: agrega únicamente decisiones listas para revisión o `RETIRE` pendiente de seguimiento;
- UI local: botón **Revisar decisiones** y endpoint GET company-scoped.

## Seguridad y autoridad

- Proyección local y read-only.
- Sin provider reads.
- Sin provider mutations.
- Sin business mutations.
- Sin generación IA.
- Sin polling.
- Sin causal inference.
- Sin scoring automático de éxito.
- Sin ejecución automática de decisiones.

## Release boundary

Este incremento pertenece exclusivamente a la cadena de desarrollo post-W99. No modifica `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, `service.py`, `version.py`, builders W99, el candidato físico ni el intent de tag `v0.9.0`. No constituye W100 ni cambia el gate físico del issue #113.
