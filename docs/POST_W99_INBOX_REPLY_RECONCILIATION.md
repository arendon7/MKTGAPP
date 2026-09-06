# Post-W99 Inbox Reply Reconciliation

## Problema cerrado

Wave41 bloquea correctamente un segundo envío cuando un intento de respuesta queda en `SENDING` o `AMBIGUOUS`, porque la app no puede afirmar si Meta recibió el efecto. Después de #166 ese estado llega a Action Center y Hoy como bloqueo HIGH, pero no existía una salida operativa segura después de que el operador verificara Meta manualmente.

Este incremento añade una reconciliación humana explícita sin convertir la app en árbitro de un resultado que no observó.

## Contrato

1. El operador actualiza Inbox explícitamente desde Meta.
2. Si existe un único checkpoint local `SENDING` o `AMBIGUOUS`, la interacción muestra una tarjeta de reconciliación.
3. El operador verifica directamente en Meta qué ocurrió.
4. Sólo entonces elige:
   - **Sí, se envió** → `RECONCILED_SENT`.
   - **No se envió** → `RETRY_ALLOWED`.
5. Cada decisión exige un `window.confirm` y el POST local exige `provider_checked: true`.

La reconciliación no llama a Meta, no reenvía contenido y no activa polling.

## Anti-retry ciego

La identidad histórica Wave41 incluye hash del texto. Antes de este hardening, un intento ambiguo con texto A podía quedar bloqueado para A pero una variante B podía producir otra clave. Ahora `InboxReplyStore.begin()` inspecciona toda la interacción: cualquier `SENDING` o `AMBIGUOUS` bloquea un nuevo envío aunque el texto cambie.

Por tanto, la única devolución de autoridad después de una ambigüedad es una reconciliación humana explícita con resultado `NOT_SENT`.

## Optimistic concurrency

El navegador no recibe `checkpoint.key` ni `text_sha256`. Recibe únicamente:

- stage observado;
- `updated_at` observado.

El POST de reconciliación debe presentar exactamente ambos valores. El store exige además que exista exactamente un intento bloqueante para la interacción. Si el estado cambió o existen varios intentos históricos, la operación falla cerrada y requiere un nuevo refresh/revisión manual.

## Resultado SENT

`RECONCILED_SENT` significa específicamente que el operador verificó Meta y confirmó que la respuesta ya se envió. No se inventa un `remote_id` y no se transforma esa constatación humana en una falsa confirmación API.

Este estado:

- retira el bloqueo de Hoy/Action Center;
- suprime la interacción como pendiente;
- deshabilita una segunda respuesta para el mismo ID de interacción;
- no persiste cuerpo del mensaje ni texto de respuesta.

## Resultado NOT_SENT

`RETRY_ALLOWED` significa que el operador verificó Meta y confirmó que el efecto no ocurrió.

La transición no envía nada. Sólo elimina el bloqueo de ambigüedad. Un nuevo intento requiere después otra acción humana independiente sobre **Enviar respuesta**, pasando nuevamente por todas las validaciones Wave41.

## API local

`POST /api/companies/{company_id}/inbox/reply-reconcile`

Campos exactos:

- `kind`;
- `interaction_id`;
- `expected_stage`;
- `expected_updated_at`;
- `outcome` (`SENT` o `NOT_SENT`);
- `provider_checked: true`.

La respuesta es secret-free y declara `provider_call_performed: false`. No expone checkpoint key, hash del texto ni remote ID.

## Evidencia

La timeline registra `social.inbox.reply.reconciled` con identidad de empresa/interacción, stage observado, resultado y flags de seguridad. No registra cuerpo del mensaje, hash del texto, checkpoint key ni remote ID.

## Límites

- no consulta Meta automáticamente;
- no resuelve múltiples intentos históricos por heurística;
- no reenvía al reconciliar;
- no añade daemon ni polling;
- no añade un cuarto workflow;
- no cambia CRM automáticamente;
- no usa IA para decidir el resultado.

Este trabajo pertenece exclusivamente al desarrollo post-W99. `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` permanece congelado; no constituye UAT física, release ni W100.
