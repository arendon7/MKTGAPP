# Wave 59 · Local Product Integration & Operational UX

## Decision

BINARIO Marketing IA remains a **local-first macOS application**. Its core product does not require Supabase, Vercel, a public backend, or a SaaS deployment.

Wave 57 and Wave 58 are preserved as deferred optional-cloud work for a future 24/7 public intake use case. They are not prerequisites for Wave 59 or later local-product work.

## Canonical local workflow

The primary product flow is:

1. **Atender** — Inbox, lead intake and daily priorities.
2. **Convertir** — CRM contacts, opportunities and follow-ups.
3. **Planear** — campaigns and audiences.
4. **Crear** — Creative Studio and Video Studio.
5. **Distribuir** — editorial calendar, explicit publishing and paid-media preparation.
6. **Aprender** — analytics, learning evidence and AI Copilot recommendations.

The active company remains the authoritative context across these surfaces.

## Local vs external capabilities

### Core local

Company state, campaigns, CRM, lead intake, creative metadata, Video Studio projects/renders, calendar, local analytics state, attribution evidence, AI session history and operational command-center state live in the local product data root.

### Explicit external connections

Meta and cloud AI providers remain integrations invoked by their existing certified actions. Wave 59 adds no automatic provider calls, no browser-held provider secrets and no new remote mutation surface.

### Optional cloud

Public Intake Gateway / Supabase / Vercel are only relevant when an Internet-facing form must receive events while the local Mac/app is unavailable. This capability remains present for future use but is grouped under advanced optional integrations and is not part of normal local readiness.

## UX integration

Wave 59 groups existing certified modules by operator intent instead of implementation wave:

- **Trabajo diario:** Hoy, Inbox, Leads, CRM.
- **Crear y distribuir:** Campañas, Creative Studio, Video Studio, Calendario, Publicar, Pauta.
- **Medir y mejorar:** Resultados, Learning/AI surfaces when present.
- **Configuración:** Audiencias, Empresas & Meta.
- **Avanzado · opcional:** attribution/capture/public 24/7 gateway surfaces.

The home screen adds a local-first explanation, high-frequency actions and a six-step journey based on existing Command Center state. It does not duplicate business engines.

## Safety and release boundary

Wave 59 does not:

- expose the desktop outside loopback by default;
- add background polling;
- automatically convert CRM leads;
- automatically send replies or messages;
- automatically publish content;
- automatically activate paid media or spend budget;
- add a fourth GitHub Actions workflow;
- require Supabase/Vercel credentials for normal startup or local operation.

Release status remains fail-closed at `0.9.0.dev1` until the separate distribution and physical UAT gates are completed.
