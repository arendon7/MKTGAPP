# Post-W99 · Global Navigator

## Boundary

`Global Navigator` continúa exclusivamente en `dev/post-w99-action-center`, sobre la cadena post-W99 nacida de `main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`.

No modifica `main`, no reconstruye el candidato W99, no crea W100 y no cambia la autoridad de release.

## Problema

El producto ya contiene CRM, leads, pipeline, campañas, seguimientos y biblioteca de contenido. A medida que crecen los datos, navegar primero al módulo correcto y luego localizar el objeto consume tiempo y rompe el flujo de trabajo.

## Solución

`GET /api/companies/{company_id}/navigator?q=...` crea una búsqueda transversal y estrictamente company-scoped sobre:

- contactos;
- oportunidades;
- leads;
- campañas;
- actividades/seguimientos;
- media/contenido.

La UI añade un disparador en el encabezado y atajo `⌘K` / `Ctrl+K`. Cada resultado abre el módulo canónico propietario; Navigator no modifica el objeto.

## Matching contract

La búsqueda es determinística: normalización de mayúsculas/minúsculas y tildes, exact match, prefijo, substring y tokens. **No usa fuzzy matching, embeddings, búsqueda semántica, LLM ni ranking de IA.**

El score solo ordena calidad textual de la coincidencia. No puntúa valor comercial, probabilidad de cierre ni prioridad operativa.

## Seguridad

La respuesta solo devuelve campos de presentación mínimos, razón de match y navegación. No hace lecturas de providers externos, no muta estado, no ejecuta acciones y no requiere nube.
