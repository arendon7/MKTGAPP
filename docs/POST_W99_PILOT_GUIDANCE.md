# Post-W99 Pilot Guidance · readiness transversal

## Alcance

Este incremento pertenece únicamente al desarrollo post-W99 y a `serve-dev`. No modifica el candidato congelado de `main`, no publica una release y no declara el producto listo para producción.

`main` permanece congelado en:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Este estado continúa siendo **not production ready**.

## Problema de piloto

W50 Command Center ya es la autoridad canónica de readiness, pero durante una operación cotidiana el usuario puede entrar directamente a Inbox, Publicar, Campañas, Pauta, Resultados, Contenido, CRM o Calendario. Cuando la empresa todavía no está preparada, esos módulos pueden mostrar estados vacíos, botones no disponibles o errores propios sin explicar inmediatamente cuál paso de preparación falta.

No se crea un segundo motor de readiness para resolverlo.

## Solución

`pilot-guidance.js` consume la proyección local y read-only existente:

`GET /api/portfolio/companies`

Esa proyección ya reutiliza W50 y entrega por empresa:

- estado de readiness;
- conteo y porcentaje;
- pasos ordenados por la autoridad W50;
- primera acción pendiente (`next_action`);
- destino propietario de la acción.

La guía sólo aparece cuando existe una empresa concreta seleccionada. En modo `Todas las empresas` no se añade una segunda capa de portfolio.

## Estados

### READY

La guía muestra de forma discreta que W50 reporta los pasos completos. Esto no implica que una publicación, proveedor o campaña haya sido ejecutada ni que un servicio remoto esté disponible en ese instante.

### NEEDS_SETUP

La guía muestra:

- progreso local;
- primer paso pendiente ya ordenado por W50;
- chips de pasos;
- CTA hacia el módulo propietario indicado por `next_action`.

Para pasos de configuración Meta/Facebook/Instagram/Ads, la navegación termina en la empresa exacta dentro de `Empresas`. Sólo después del clic explícito del operador ese módulo propietario puede realizar sus verificaciones remotas existentes.

### LOCAL_STATE_ERROR

No se infiere disponibilidad de Meta ni de los módulos. Se ofrece una nueva lectura local y acceso explícito a la empresa.

## Vistas cubiertas

La guía acompaña el recorrido principal del piloto con empresa exacta:

- Hoy;
- Empresas;
- Contenido;
- Calendario;
- CRM;
- Inbox;
- Resultados;
- Campañas;
- Pauta;
- Publicar.

No cambia la autoridad funcional de ninguna de esas vistas.

## Contratos de seguridad

Este incremento:

- reutiliza W50; no crea ni copia su motor de readiness;
- sólo lee `GET /api/portfolio/companies`;
- no hace provider reads automáticos;
- no llama `/api/meta/*` desde la nueva capa;
- no realiza POST, PATCH ni DELETE;
- no publica contenido;
- no modifica CRM;
- no activa campañas ni pauta;
- no ejecuta IA;
- no añade polling periódico;
- no usa `MutationObserver`;
- no serializa credenciales, tokens ni IDs remotos.

Las mutaciones y verificaciones remotas siguen perteneciendo al módulo dueño y requieren una empresa exacta.

## Runtime

El terminal acumulativo de desarrollo avanza a:

`service_post_w99_pilot_guidance_app`

La nueva capa se carga después de `pilot-readiness.js`, conservando la identidad y entrada de piloto del incremento anterior.

El `serve` canónico y `main` permanecen fuera de este cambio.
