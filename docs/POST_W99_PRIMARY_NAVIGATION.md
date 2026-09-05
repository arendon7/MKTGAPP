# Post-W99 · Primary Navigation Consolidation

## Purpose

This increment reduces the visible product navigation without deleting or replacing any existing marketing capability. The operator should see a small stable set of daily destinations while specialist modules remain reachable on demand.

## Primary navigation

The canonical visible destinations are:

1. `Hoy` → `today-execution`
2. `Empresas` → `companies`
3. `Contenido` → the existing content/Creative Studio surface
4. `Calendario` → `calendar`
5. `CRM` → `crm`
6. `Inbox` → `inbox`
7. `Resultados` → `intelligence`

`Astra / IA` remains a permanent explicit action. It returns to the existing AI Copilot surface; it does not create a second AI runtime or new authority.

## Secondary navigation

A compact `Más` selector preserves direct access to specialist surfaces:

- Executive Cockpit;
- Action Center;
- Campaigns;
- Paid Media;
- Publish;
- Video Studio;
- Audiences;
- Analytics.

These modules are hidden from the primary row only. Their routes, state, endpoints, contracts, ownership and deep links remain unchanged.

## Product contract

This layer is presentation-only:

- no new business endpoint;
- no provider read or write;
- no CRM mutation;
- no publication or message send;
- no campaign execution;
- no new persistence key;
- no reprioritization;
- no background polling;
- no automatic AI generation;
- no replacement of Action Center, Today, Cockpit, Results Intelligence or owner modules.

The existing product modules remain authoritative for their own actions and evidence.

## Why this change

The post-W99 branch already contains mature operator surfaces such as Today Execution, Executive Cockpit, Action Center, CRM, Results Intelligence and contextual handoffs. The previous navigation continued exposing implementation-level modules as equal top-level destinations. This increment aligns the shell with the intended one-person, multi-company workflow while retaining advanced access.

## Release boundary

This increment exists only on the post-W99 development line. Canonical `main` remains frozen at:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

It does not modify `service.py`, `version.py`, release builders, release workflows, the W99 physical candidate, or tag intent `v0.9.0`.

**No es W100.** It grants no Physical-UAT PASS, release authority, publication authority or production-ready status.
