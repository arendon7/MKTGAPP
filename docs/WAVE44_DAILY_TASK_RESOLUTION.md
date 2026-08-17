# Wave 44 · Daily Task Resolution

Wave 44 convierte `HOY · PRIORIDADES` en una superficie de resolución operativa explícita sin introducir automatización remota nueva.

## Acciones permitidas

- Seguimiento CRM: `Completar` requiere confirmación y reutiliza el endpoint local certificado `POST /api/companies/{company_id}/activities/{activity_id}/complete`.
- Seguimiento CRM: `Abrir` lleva directamente a la pestaña Seguimientos del CRM.
- Publicación: `Gestionar` abre la publicación exacta en el panel editorial Wave 42.

## Acciones prohibidas desde Inicio

- publicar o reintentar automáticamente;
- responder mensajes/comentarios automáticamente;
- llamadas directas a Meta;
- polling, timers o MutationObserver para trabajo de fondo;
- cambios implícitos sin click y confirmación del usuario.

## Invariantes

1. La única mutación directa desde `daily-actions.js` es completar una actividad CRM local.
2. Gestionar una publicación no produce side effects remotos; cualquier corrección/reprogramación/cancelación sigue pasando por el flujo editorial existente.
3. El FULL MAC debe lanzar `service_wave44_app` y ejecutar `audit_wave44_daily_actions.sh`.
4. Source CI debe validar sintaxis JS, tests y contratos en Ubuntu + macOS; PR CI debe validar FULL MAC arm64 + x86_64.
