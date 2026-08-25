# Post-W99 · Executive Marketing Cockpit

## Purpose

Executive Marketing Cockpit crea una sola lectura ejecutiva por empresa sobre las superficies post-W99 ya existentes. Su objetivo es responder, sin saltar primero entre módulos:

1. qué está bloqueado;
2. qué requiere atención;
3. qué ocurre en el pipeline;
4. qué resultado comercial está atribuido con evidencia exacta;
5. qué campañas requieren intervención;
6. qué decisiones humanas están listas para revisión o pendientes de seguimiento.

El Cockpit **no reemplaza** Action Center, CRM, Results Intelligence, Commercial Outcome Intelligence ni Decision Review. Es un read model agregado; los módulos fuente conservan autoridad sobre orden, evidencia y ejecución.

## Estado ejecutivo

El estado global usa únicamente tres clasificaciones determinísticas:

- `BLOCKED`: existe al menos un bloqueante o prioridad crítica ya detectada por Action Center.
- `ATTENTION`: no hay bloqueo, pero alguna dimensión comercial, de campaña o decisión tiene atención explícita pendiente.
- `STABLE`: no existen bloqueos ni alertas determinísticas en las cuatro dimensiones.

No existe un porcentaje de salud, score compuesto, ponderación oculta ni ranking de valor de negocio.

## Cuatro dimensiones

### Operación

Proviene de Action Center. El Cockpit conserva su orden y su `next_action` exactos.

### Comercial

Proviene del Commercial Pipeline y Commercial Outcome Intelligence. Puede mostrar oportunidades abiertas, seguimientos pendientes, leads capturados, oportunidades atribuidas y ganadas atribuidas.

La atención del pipeline se basa en condiciones explícitas como vencimiento, ausencia de siguiente acción o seguimiento sin fecha. No es forecast ni probabilidad de cierre.

### Campañas

Proviene de Results Intelligence: campañas activas, atención requerida, evidencia observada, atribución y decisiones humanas registradas.

### Decisiones

Proviene de Decision Review. Distingue revisión por evidencia posterior y seguimiento de decisiones `RETIRE` que todavía no fueron ejecutadas explícitamente.

La presencia de evidencia posterior no prueba causalidad.

## Dinero y atribución

Los valores permanecen separados por moneda. El Cockpit puede mostrar, por ejemplo, pipeline COP y pipeline USD en filas diferentes, pero nunca suma ambas monedas.

La atribución CRM conserva `LAST_CAPTURED_TOUCH` y tracking exacto first-party. No hay matching probabilístico ni inferencia temporal por coincidencia de nombres o fechas.

## Evidence freshness

La vista muestra el último snapshot persistido cuando existe. Abrir el Cockpit:

- no consulta providers;
- no refresca Meta ni otras plataformas;
- no asume que la evidencia remota siga fresca;
- no convierte el timestamp local del Cockpit en timestamp de provider.

## UI

La navegación post-W99 incorpora `Cockpit / Executive`. La pantalla incluye:

- estado ejecutivo;
- cuatro lanes de salud determinística;
- executive brief basado en señales existentes;
- pipeline e impacto atribuido;
- top actions en el mismo orden de Action Center;
- campañas, evidencia y gobierno de decisiones.

Toda navegación abre el módulo canónico responsable.

## Safety contract

Executive Cockpit es GET-only y read-only:

- no publica;
- no envía mensajes;
- no mueve oportunidades;
- no archiva campañas;
- no ejecuta decisiones;
- no realiza provider reads o writes;
- no genera IA;
- no hace polling de fondo;
- no infiere causalidad, probabilidad de cierre ni forecast;
- funciona sin score de salud inventado.

## Release boundary

Este incremento vive únicamente en la línea de desarrollo post-W99. `main` permanece congelado en:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

No modifica `service.py`, `version.py`, builders, workflows de release, candidato físico W99 ni intent de tag `v0.9.0`.

**No constituye W100**, release candidate, release authority ni production-ready. El gate físico del issue #113 continúa siendo independiente y obligatorio para W99.
