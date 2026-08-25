# Post-W99 · Development Entrypoint

## Purpose

La rama `dev/post-w99-action-center` conserva dos runtimes deliberadamente distintos:

- `binario-marketing serve` → runtime canónico/release existente; no cambia.
- `binario-marketing serve-dev` → entrypoint estable de la cadena post-W99 de desarrollo.

`serve-dev` resuelve `service_post_w99_dev_app`, que actualmente carga Action Center + Pipeline Priority + Global Navigator + Commercial Outcome Intelligence + Decision Review + Portfolio Control Tower + Executive Marketing Cockpit + Today / Operator Execution + Execution Return Flow + Contextual Deep Linking + Evidence Observability.

Las superficies superiores son deliberadamente complementarias:

- **Portfolio Control Tower** responde qué empresa requiere atención primero y conserva el orden transversal de Action Center.
- **Executive Marketing Cockpit** responde qué está pasando dentro de la empresa seleccionada en Operación, Comercial, Campañas y Decisiones.
- **Today / Operator Execution** toma como máximo los primeros cinco elementos del Action Center de esa empresa, sin reordenarlos, para convertir la prioridad ya decidida en una secuencia diaria ejecutable.
- **Execution Return Flow** conserva de forma efímera el contexto de navegación cuando una acción se abre desde Today y permite volver al plan después de ejecutar en el módulo propietario. Al regresar relee Today y Action Center; nunca usa el contexto de navegador como estado de completitud.
- **Contextual Deep Linking** usa únicamente los IDs canónicos ya presentes en la acción para enfocar el registro exacto dentro del módulo propietario. Si no existe identidad suficiente o el registro no está presente en la lectura local, abre el owner sin adivinar un sustituto.
- **Evidence Observability** muestra qué evidencia local existe, cuándo fue observada y dónde la cobertura es parcial/no observada/unknown. No consulta proveedores, no califica desempeño y no altera prioridad ni completitud.

`service_post_w99_execution_return_app` conserva el contexto de retorno. `service_post_w99_contextual_deep_linking_app` agrega navegación exacta. `service_post_w99_evidence_observability_integrated_app` es ahora el terminal de composición de `serve-dev`: hereda toda esa cadena, reutiliza el proyector read-only de Evidence Observability y agrega únicamente su endpoint/UI.

La secuencia de browser bootstraps queda: `Today → Execution Return → Contextual Deep Linking → Evidence Observability`.

Esto permite seguir construyendo producto mientras `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` y su candidato físico W99 permanecen congelados para la UAT del issue #113.

## Defaults

`serve-dev` usa loopback `127.0.0.1` y puerto `8766` por defecto. Igual que el runtime canónico, rechaza binds no-loopback salvo `--allow-network` explícito.

## Contract

El comando de desarrollo no cambia `service.py`, `version.py`, el tag intent `v0.9.0`, los builders W99 ni el artefacto físico. No debe interpretarse como W100, release candidate ni production-ready.
