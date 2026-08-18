# Wave 47 · Product Surface Reconstruction

## Hallazgo de UAT

La UAT física confirmó una brecha entre **capacidad técnica** y **producto visible**. El repositorio ya contiene motores profundos de video, Meta, pauta, campañas, CRM, audiencias, analítica e inbox, pero varias capacidades quedaron distribuidas entre el Workspace histórico, paneles de proyecto y extensiones sucesivas.

El problema principal ya no es “crear más módulos”; es convertirlos en un sistema de mercadeo coherente, company-first y navegable.

## Arquitectura objetivo

La **empresa activa** es la raíz operativa. Cada empresa conecta:

1. estrategia/campañas;
2. Creative Studio y biblioteca;
3. distribución orgánica/calendario;
4. Paid Media;
5. CRM/audiencias;
6. analítica/inbox;
7. prioridades de hoy.

No se debe pedir al usuario entender la diferencia interna entre `ProjectStore`, `CompanyStore`, stores sociales o motores de video.

## Wave 47

### Empresa activa
- el selector superior deja de ser un filtro opcional y se convierte en contexto persistente;
- si no existe una selección válida se recupera la última empresa o se selecciona la primera;
- el dashboard muestra salud de Meta, redes y cuenta publicitaria.

### Empresas & Meta
- conectar/desconectar Meta directamente desde la capa de empresa;
- credencial continúa en Keychain;
- descubrir Páginas/Instagram/cuentas Ads;
- asociar los activos seleccionados a la empresa activa.

### Company Marketing Studio
- una empresa recibe un único proyecto creativo persistente mediante `CompanyWorkspaceStore`;
- Video Studio, assets, transcripción, renders y Paid Media reutilizan ese proyecto certificado;
- no se duplican FFmpeg, Whisper, ProjectStore ni PaidMediaStore.

### Video Studio
- módulo principal en navegación y dashboard;
- abre directamente el workspace creativo de la empresa;
- flujo rápido para cargar un video y comenzar.

### Pauta
- módulo principal, no una tarjeta escondida dentro del editor;
- el browser no puede elegir arbitrariamente otra cuenta publicitaria/Página: la identidad Meta asociada a la empresa es autoritativa;
- permite guardar borradores y crear Campaign + Ad Set + Creative + Ad en Meta;
- toda estructura remota se crea en `PAUSED`;
- no existe activación automática ni gasto desde este gate.

### Iteración Mac
- el workflow diario FULL MAC pasa a arm64-only;
- Intel queda fuera de las iteraciones normales para reducir ciclo de feedback;
- Source CI sigue verificando contratos en macOS y Ubuntu;
- una certificación multi-arquitectura podrá reactivarse más adelante como gate de distribución, no como costo de cada cambio.

## Roadmap controlado

### Wave 48 · Paid Media Center profundo
- campaña de marketing ↔ plan de pauta explícitamente relacionados;
- creativos desde biblioteca/render, eliminando dependencia innecesaria de URL manual;
- targeting más completo y validado;
- presupuesto/moneda/periodo y estimaciones claramente separados;
- observabilidad/readback de Campaign, Ad Set, Creative y Ad;
- estados y errores recuperables;
- activación sigue bloqueada hasta diseñar aprobación específica.

### Wave 49 · Creative Studio consolidado
- biblioteca de empresa como entrada única;
- Video Studio, clips rápidos, transcripción y renders desde el shell;
- outputs pasan directamente a campañas, calendario y pauta;
- reducir navegación al Workspace legado y ocultar complejidad técnica innecesaria.

### Wave 50 · Marketing OS Dashboard
- objetivos y campañas activas;
- contenido listo/pendiente;
- pauta DRAFT/PAUSED y performance;
- CRM y conversiones;
- inbox y señales sociales;
- prioridades accionables y aprendizaje de campaña.

## Regla de desarrollo

A partir de Wave 47 una wave solo se justifica si reduce una brecha visible del producto o cierra un gate de confiabilidad. No se abren capacidades aisladas que no tengan una ubicación clara en la arquitectura company-first.
