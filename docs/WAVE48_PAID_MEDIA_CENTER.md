# Wave 48 · Paid Media Center

Wave 48 convierte Pauta en un centro company-first que conecta estrategia, creativo, presupuesto, targeting, ejecución PAUSED y observabilidad remota.

## Plan de pauta

Cada `PaidMediaDraft` mantiene su contrato histórico y recibe metadata aditiva en `PaidMediaPlanStore`:
- campaña de marketing vinculada;
- fuente del creativo (`company_media` o `public_url`);
- medio gestionado y `image_hash` remoto cuando aplica;
- moneda reportada por la cuenta;
- inicio/fin del plan;
- preset de insights;
- notas/hipótesis.

No se migran destructivamente los JSON históricos de Paid Media.

## Creativo gestionado

Una imagen ya almacenada en la biblioteca de la empresa puede usarse sin obligar al usuario a publicar una URL externa:
1. se valida ownership e integridad local;
2. se carga a `/adimages` de la cuenta publicitaria;
3. se persiste el `image_hash` retornado por Meta;
4. el Ad Creative usa `link_data.image_hash`.

La URL `managed.binario.invalid` existe únicamente como compatibilidad interna con el schema histórico del draft y nunca se usa para crear el creativo remoto cuando `source_kind=company_media`.

## Presupuesto

`daily_budget` conserva el contrato del Marketing API ya usado por el motor: entero positivo en la unidad monetaria menor aceptada por la cuenta publicitaria. La UI muestra la moneda reportada por el Ad Account y deja explícito que Binario no realiza conversiones monetarias implícitas.

No se debe reinterpretar el número como una conversión automática a pesos/dólares/euros.

## Periodo

`start_at` y `end_at` son opcionales, timezone-aware y se aplican al Ad Set. Cuando ambos existen, `end_at > start_at` es obligatorio.

## Ejecución remota

La jerarquía sigue siendo recuperable mediante checkpoints:
- Campaign → `PAUSED`;
- Ad Set → `PAUSED`;
- Creative → creado desde URL pública o `image_hash`;
- Ad → `PAUSED`.

Cada ID remoto se persiste antes de crear el siguiente objeto.

## Observabilidad

El Paid Media Center reutiliza la observabilidad read-only existente y muestra:
- presencia/estado de Campaign, Ad Set, Creative y Ad;
- IDs remotos;
- impresiones, reach, clicks, spend, CTR, CPC, CPM y frecuencia cuando Meta los reporta;
- campaña de marketing y plan local asociados.

Si Meta reporta un objeto configurado `ACTIVE`, la UI lo trata como anomalía externa y lo muestra explícitamente.

## Safety lock

Wave 48 NO añade:
- endpoint `/activate`;
- cambio automático a `ACTIVE`;
- auto-spend;
- polling en background;
- publicación social automática;
- modificación silenciosa de la cuenta Ads/Página asociada a la empresa.

La empresa activa sigue siendo la autoridad sobre Page/Instagram/Ad Account.

## Gate arm64

El `.app` actual se arma desde `build_full_mac_current.sh`. El workflow conserva el smoke histórico completo en arm64 y el build current debe incluir y auditar Wave 47 + Wave 48 antes de firmar el candidato de iteración.
