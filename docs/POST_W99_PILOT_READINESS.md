# Post-W99 Pilot Readiness · entrada operativa

## Alcance

Este incremento pertenece exclusivamente a la rama de desarrollo post-W99 y a `serve-dev`. No modifica el candidato congelado de `main`, no publica una release y no declara el producto listo para producción.

`main` permanece congelado en:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

## Objetivo

Reducir la fricción del primer arranque para una prueba operativa controlada de MERCADEO APP:

- identidad coherente en navegador y cabecera;
- favicon estable;
- indicador visible `Piloto local`;
- entrada guiada al módulo correcto;
- recuperación visible cuando la cadena de interfaz no termina de cargar.

## Entrada de piloto

El runtime de desarrollo sirve una capa de presentación sobre el HTML histórico sin modificar sus motores ni autoridades de negocio.

Reglas de entrada:

1. Si todavía no existen empresas, la aplicación abre `Empresas`, donde vive el onboarding multiempresa y cada configuración termina en el módulo propietario de la empresa.
2. Si ya existe al menos una empresa, la aplicación abre `Hoy` (`today-execution`), cuya capa portfolio muestra el foco transversal multiempresa.
3. Si el operador ya navegó a otra vista durante el arranque, la capa de piloto no sustituye esa elección.

## Identidad

Sólo en `serve-dev`:

- título: `MERCADEO APP · Centro de operaciones`;
- cabecera: `MERCADEO APP / Centro de operaciones`;
- favicon local `/favicon.svg`;
- etiqueta `Piloto local`.

Esto no cambia el paquete ni la autoridad de release W99.

## Recuperación de arranque

La capa escucha el evento existente `wave73-bootstrap-failed`. Ante un fallo de la cadena visual muestra un estado degradado explícito y una acción de recarga, en lugar de dejar una interfaz aparentemente incompleta o silenciosa.

No intenta reparar datos, ejecutar acciones ni reintentar proveedores automáticamente.

## Contratos de seguridad

Este incremento es de presentación y navegación solamente:

- no realiza provider reads;
- no realiza provider mutations;
- no publica contenido;
- no modifica CRM;
- no crea ni activa pauta;
- no ejecuta IA;
- no introduce polling nuevo;
- no introduce una nueva autoridad de readiness;
- no altera W50, W35, W48, W64, W65 ni las autoridades existentes de Contenido, Media, Scheduler o CRM.

Las acciones que requieren cambios siguen delegándose al módulo dueño y a una empresa concreta.

## Separación de release

El terminal acumulativo de desarrollo avanza a `service_post_w99_pilot_readiness_app`, utilizado por `serve-dev`.

El `serve` canónico y `main` permanecen fuera de este incremento. Este estado es apto para continuar preparación y validación de piloto local, **not production ready**.
