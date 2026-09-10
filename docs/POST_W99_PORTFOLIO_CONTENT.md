# Post-W99 · Portfolio Content

## Estado de release

`main` permanece congelado en W99: `60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`.

Este incremento pertenece exclusivamente a `dev/post-w99-action-center`; no crea W100, tag, GitHub Release ni autoridad de publicación.

## Hallazgo de arquitectura

El Calendario ya es multiempresa: cuando el filtro superior está en **Todas las empresas**, `refreshMarketingOps()` consulta `/api/ops/calendar` sin `company_id` y la vista existente muestra fecha, empresa, canal, contenido y estado.

Por tanto, este incremento no crea un segundo calendario ni un segundo scheduler.

## Qué añade

`GET /api/portfolio/content` compone una lectura local de todas las empresas reutilizando `creative_context(company_id)` de Creative Studio.

La proyección presenta:

- activos creativos por empresa;
- estados efectivos `UNPROFILED`, `BRIEF`, `DRAFT`, `READY`, `SCHEDULED`, `PUBLISHED`, `PAID`, `ARCHIVED`;
- campaña vinculada cuando existe;
- canales;
- número de publicaciones y pautas vinculadas;
- fecha programada proveniente de la publicación canónica;
- handoff a la biblioteca de la empresa propietaria.

La UI `web/portfolio-content.js` convierte **Contenido** en una vista transversal por defecto y permite volver al contenido de la empresa exacta para cargar, eliminar, preparar o reutilizar archivos.

El botón **Calendario global** limpia el filtro de empresa y abre el calendario editorial multiempresa ya existente.

## Autoridades preservadas

- **Company Media** conserva autoridad sobre archivos.
- **Creative Studio** conserva autoridad sobre estado creativo.
- **Social Publications / Scheduler** conserva autoridad sobre programación y publicación.
- **Calendario editorial existente** conserva la proyección temporal.
- **Paid Media** conserva autoridad de pauta.
- Portfolio Content sólo lee y enruta.

No hay `POST`, `PATCH` ni `DELETE` nuevos en la vista transversal.

## Seguridad

La proyección omite campos innecesarios como hashes completos, rutas de archivo, notas creativas, `remote_id` de proveedores y presupuestos internos de campaña.

No ejecuta:

- lecturas de proveedor;
- mutaciones de proveedor;
- carga/eliminación de contenido;
- publicación;
- programación;
- generación IA;
- polling en background.

## Desarrollo

```bash
PYTHONPATH=src python3 -m binario_marketing.cli serve-dev --host 127.0.0.1 --port 8766 --open
```

La cadena sigue manteniendo exactamente tres workflows GitHub canónicos.
