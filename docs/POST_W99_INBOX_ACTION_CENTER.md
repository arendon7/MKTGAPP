# Post-W99 Inbox → Action Center

## Problema cerrado

La Bandeja social ya podía leer Messenger y comentarios de Instagram, vincular identidades exactas con CRM, crear seguimientos locales y enviar respuestas manuales. Sin embargo, esa evidencia existía sólo en la sesión del navegador después de pulsar **Actualizar desde Meta**. `Today`, `Action Center` y el portafolio multiempresa no podían verla sin volver a consultar al proveedor.

Este incremento conecta la bandeja con la cola operativa sin crear otro motor de prioridad y sin introducir polling.

## Flujo

1. El operador abre **Inbox** y pulsa **Actualizar desde Meta**.
2. El terminal post-W99 ejecuta el lector Meta existente una sola vez.
3. La respuesta completa sigue llegando al navegador para la experiencia Wave39–41.
4. En paralelo se crea un snapshot local mínimo `binario.marketing.inbox-attention-snapshot.v1`.
5. `Action Center` consume exclusivamente ese snapshot local, CRM local y checkpoints de reply locales.
6. `Portfolio Control Tower` y **Hoy multiempresa** heredan automáticamente las nuevas filas porque Action Center continúa siendo la autoridad de orden.

## Minimización durable

El snapshot conserva como máximo 40 candidatos y únicamente:

- empresa;
- fecha de captura;
- tipo de interacción;
- ID estable de la interacción;
- fecha de la interacción;
- `@usuario` cuando Meta lo entrega;
- ID de contacto CRM exacto cuando ya existe;
- extracto máximo de 280 caracteres;
- elegibilidad observada para respuesta.

No persiste:

- access tokens ni otros secretos;
- IDs personales del proveedor;
- listas `from/to` completas;
- enlaces de conversaciones;
- IDs de media usados sólo para la lectura;
- errores/warnings textuales de Meta;
- cuerpos completos de mensajes/comentarios;
- remote IDs de respuestas.

Para Messenger sólo se conserva el mensaje más reciente de cada conversación y únicamente si ese mensaje más reciente es entrante. Si la última evidencia es una respuesta saliente de la Página, esa conversación no entra como trabajo pendiente.

## Prioridad y deduplicación

No existe un segundo score. Las filas se insertan en la cola ya existente con ranks deterministas:

- intento de reply `SENDING`/`AMBIGUOUS`: HIGH, rank 18, requiere verificación antes de reenviar;
- Messenger entrante todavía elegible dentro de la ventana conservadora: HIGH, rank 27;
- comentario Instagram: MEDIUM, rank 45;
- mensaje que requiere triage pero ya no es elegible para respuesta: MEDIUM, rank 47;
- snapshot ausente, futuro o mayor de 12 h: LOW, rank 76, **Actualizar bandeja social**.

Una interacción no se vuelve a mostrar cuando:

- existe una actividad CRM con el marker Wave40 exacto (`MKTGAPP_META_MESSAGE` / `MKTGAPP_META_COMMENT`); o
- existe un checkpoint Wave41 `SENT` para esa interacción.

Los checkpoints corruptos nunca se interpretan como `SENT` y por tanto nunca ocultan trabajo.

## Semántica de refresh

`GET /api/companies/{company_id}/inbox/attention` es local y no consulta proveedores.

`POST /api/companies/{company_id}/inbox/refresh-attention` es la única nueva ruta que ejecuta una lectura Meta. Se invoca exclusivamente al pulsar **Actualizar desde Meta** desde el adaptador `inbox-action-center.js`.

No hay:

- refresh al cargar la app;
- `setInterval`;
- `MutationObserver` usado como disparador;
- lectura Meta desde Action Center;
- auto-reply;
- auto-creación CRM;
- auto-priorización por IA.

## Snapshot vencido

Después de 12 horas el snapshot deja de afirmar que sus interacciones siguen pendientes. Action Center retira esas filas y muestra solamente la acción de refrescar. Esto evita convertir evidencia vieja en una afirmación operativa actual.

## Multiempresa

Cada archivo de snapshot está confinado a un `company_<24 hex>` exacto. La lectura de actividades CRM y checkpoints de respuesta también se filtra por empresa. Portfolio Control Tower no cambia su algoritmo: recibe cada Action Center ya enriquecido y conserva su orden global determinista.

## Empaquetado

El bundle post-W99 de desarrollo exige y audita:

- `src/binario_marketing/inbox_attention.py`;
- `src/binario_marketing/service_post_w99_inbox_action_center_app.py`;
- `web/inbox-action-center.js`.

El smoke sólo verifica la presencia y contrato estático de estas superficies. No consulta Meta ni ejecuta el POST de refresh.

## Límites

Este incremento no hace que la bandeja se sincronice sola. El diseño continúa siendo deliberadamente explícito porque una lectura Meta implica red y credenciales. La mejora consiste en que **Hoy sabe cuándo la evidencia falta o está vieja y puede mostrar las interacciones capturadas en el último refresh explícito**, eliminando la necesidad de entrar a Inbox simplemente para recordar que existe trabajo pendiente.

No se añade ningún workflow; siguen siendo exactamente `ci.yml`, `full-mac-app.yml` y `persistent-release.yml`.

Todo este trabajo pertenece al desarrollo post-W99. No cambia ni autoriza el candidato físico congelado `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`, no constituye UAT física y no crea W100.
