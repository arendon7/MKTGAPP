# Post-W99 · Results Decision Freshness Guard

## Objetivo

Cerrar una brecha operacional de Wave 65: una campaña activa con distribución podía conservar un snapshot histórico durante un tiempo indefinido y seguir ofreciendo `RECORD_DECISION` o `OPTIONAL_AI`. Esta capa no invalida la evidencia histórica ni interpreta desempeño; sólo exige una actualización explícita antes de una **nueva** decisión de campaña o de un nuevo análisis IA de campaña cuando el último snapshot supera la cadencia operativa.

## Política

- Aplica sólo a campañas no terminales (`COMPLETED` / `ARCHIVED` quedan fuera) que ya tienen distribución orgánica publicada o pauta remota pausada/configurada.
- Ventana operativa: **24 horas** desde `latest_snapshot.created_at`.
- A las 24 horas exactas el snapshot todavía está dentro de ventana; después de ese punto se requiere refresh.
- Snapshot ausente, timestamp inválido o timestamp futuro no pueden autorizar una nueva decisión.
- La política es una regla de **cadencia de decisión**, no una afirmación de que los datos sean malos, irrelevantes o estadísticamente obsoletos.
- La evidencia histórica, atribución y decisiones ya registradas permanecen visibles.

## Reutilización de autoridades existentes

No se crea un nuevo motor de prioridades ni un nuevo endpoint de refresh.

1. `results_intelligence_workspace()` conserva Wave 65 y añade `evidence.operational_freshness`.
2. Si el refresh es obligatorio, la siguiente acción vuelve al código canónico `CAPTURE_RESULTS`, con la etiqueta `Actualizar resultados antes de decidir`.
3. Action Center conserva su ranking existente para `CAPTURE_RESULTS` y el `campaign_id` exacto.
4. Campaign Results Owner Handoff continúa llevando al control de Wave 52 `W52_LEARNING_REFRESH`.
5. El refresh sigue requiriendo acción/confirmación humana y es la única operación que puede leer providers para actualizar evidencia.

## Defensa contra bypass

La protección no es sólo visual:

- `record_learning_decision()` rechaza una nueva decisión `CAMPAIGN` mientras la campaña protegida requiera refresh.
- `generate_ai_copilot()` rechaza `task=CAMPAIGN` en la misma condición antes de resolver credenciales o llamar al provider IA.
- `campaign_results_owner_context()` marca `record_decision.available=false` y `optional_ai.available=false` con `blocked_reason=RESULTS_REFRESH_REQUIRED`.
- Fallos concretos de ejecución (`FIX_EXECUTION`) conservan precedencia; la necesidad de refresh queda visible pero no sustituye el blocker operativo.

## Seguridad y límites

- Sin polling.
- Sin refresh automático de Meta.
- Sin mutación de provider.
- Sin ejecución automática de decisiones.
- Sin ejecución automática de recomendaciones IA.
- Sin nueva autoridad de publicación, pauta o mensajería.
- Sin cuarto workflow de GitHub Actions.
- Sin cloud provisioning adicional.

## Frontera W99

Este incremento pertenece exclusivamente a `dev/post-w99-action-center`. No modifica ni autoriza el candidato W99 congelado:

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

No es W100, no satisface Physical UAT, no crea release y no concede `release_authority`.
