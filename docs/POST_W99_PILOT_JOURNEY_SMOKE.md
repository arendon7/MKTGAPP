# Post-W99 Pilot Journey Smoke · recorrido operativo actual

## Alcance

Este incremento pertenece únicamente al desarrollo post-W99 y a `serve-dev`. No modifica el candidato congelado de `main`, no publica una release y no declara el producto listo para producción.

`main` permanece congelado en:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Este estado continúa siendo **not production ready**.

## Problema corregido

El verificador histórico `product-journey.js` corresponde a Wave 73. Su catálogo aún contiene rutas como `video` y `analytics`, y trataba `content` como el antiguo Workspace/Editor de video mediante `opsShowLegacy()` y la existencia de un proyecto local.

Ese contrato ya no representa MERCADEO APP post-W99:

- `Contenido` es la superficie actual de contenido por empresa/portfolio;
- `Resultados` usa `intelligence`;
- `Hoy` (`today-execution`) es la entrada operativa actual;
- Inbox, CRM, Contenido, Campañas y Pauta tienen superficies multiempresa post-W99;
- Publicar requiere una empresa exacta.

No se elimina ni se modifica el archivo histórico W73. `serve-dev` carga después una capa de smoke actual que neutraliza su botón para el piloto post-W99.

## Recorrido actual

La secuencia observada es:

1. Hoy;
2. Empresas;
3. Inbox;
4. CRM;
5. Contenido;
6. Calendario;
7. Campañas;
8. Pauta;
9. Resultados;
10. Publicar, únicamente cuando existe empresa exacta seleccionada.

## Verificación pasiva

El smoke **no realiza navegación automática**.

Registra evidencia únicamente cuando el operador abre una vista. Para una visita se valida localmente:

- que la vista activa corresponda a la ruta;
- que el shell empresarial esté visible;
- que exista contenido renderizado;
- que exista el control de navegación correspondiente;
- que la navegación esté sincronizada como activa.

La evidencia vive sólo durante la sesión del navegador y se separa entre:

- `PORTFOLIO` — Todas las empresas;
- `COMPANY` — empresa exacta.

Así una visita en portfolio no certifica la superficie propietaria de una empresa concreta.

## Acción manual

El botón `Recorrido piloto` muestra el estado del recorrido. Cada fila puede ofrecer `Abrir`, pero esa navegación ocurre exclusivamente tras el clic explícito del operador.

`Publicar` aparece como `EMPRESA EXACTA` cuando el usuario se encuentra en portfolio y no cuenta como requisito pendiente en ese modo.

## Contrato de seguridad

La nueva capa:

- no hace `fetch`;
- no consume APIs;
- no llama proveedores;
- no realiza provider reads;
- no realiza provider mutations;
- no envía formularios;
- no publica;
- no modifica CRM;
- no activa campañas o pauta;
- no ejecuta IA;
- no introduce `setInterval`;
- no usa `MutationObserver`;
- no navega automáticamente por las vistas;
- no persiste evidencia en localStorage.

La única navegación programática del smoke está asociada al botón `Abrir` de una fila y por tanto a una acción humana explícita.

## Interpretación de PASS

Un PASS significa exclusivamente que una vista fue abierta manualmente y que su shell/navegación local se renderizaron de forma coherente durante esa sesión.

No demuestra:

- que Meta haya entregado una operación remota;
- que una publicación se haya ejecutado;
- que una campaña esté activa en proveedor;
- que exista evidencia física de UAT;
- que el producto esté listo para producción.

## Runtime

El terminal acumulativo de desarrollo avanza a:

`service_post_w99_pilot_journey_smoke_app`

Se carga después de `pilot-guidance.js`, conservando identidad de piloto, onboarding/readiness y guía W50 transversal.

El `serve` canónico y `main` permanecen fuera de este cambio.
