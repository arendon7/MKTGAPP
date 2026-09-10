# Post-W99 · Portfolio Campaigns + Paid Media

## Release boundary

`main` remains frozen at W99: `60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`.

This increment belongs only to `dev/post-w99-action-center`. It does not create W100, a release, a tag, publication authority, or paid-media activation authority.

## Architecture

The portfolio layer does not calculate a second campaign state.

- **W65 Results Intelligence** remains the canonical campaign intelligence/results projection.
- **W64 Execution Workspace** remains the canonical campaign execution projection.
- **W35 Campaigns** remains the owner for campaign creation and editing.
- **W48 Paid Media Center** remains the owner for paid-media planning, explicit Meta readback and explicit remote creation in `PAUSED`.

`GET /api/portfolio/campaigns` composes only local state from all companies. It calls `results_intelligence_workspace(company_id)` plus `company_paid_media(company_id)`. Neither path performs provider reads.

## Product behavior

The top company filter has a deliberate meaning:

- **Todas las empresas + Campañas** → transversal campaign portfolio.
- **Specific company + Campañas** → existing W35 campaign editor.
- **Todas las empresas + Pauta** → transversal paid-media portfolio.
- **Specific company + Pauta** → existing W48 Paid Media Center.

A portfolio card may hand the operator to Campaigns, Execution, Content, Calendar, Paid Media or Results for the exact owning company. All mutations remain in those owner modules.

## Cross-company minimization

The portfolio output includes only operational fields required to decide where to work next. It intentionally omits:

- contact identities and campaign notes;
- detailed targeting;
- ad copy and destination/media URLs;
- Meta ad account, Page and Instagram IDs;
- remote Campaign / Ad Set / Creative / Ad IDs;
- paid-media notes and image hashes;
- raw evidence and prior AI text.

It exposes booleans/counts for human decisions and AI analysis rather than copying their private payloads.

## Paid-media safety

Portfolio Paid Media is read-only. It cannot:

- create or delete a paid-media plan;
- create Meta objects;
- query Meta observability;
- activate Campaign, Ad Set or Ad;
- change spend.

Those actions remain in W48. W48's remote creation path continues to require an explicit human action and creates the hierarchy only in `PAUSED`.

## Campaign safety

Portfolio Campaigns is read-only. It cannot create/edit campaigns, publish organic content, create paid objects, generate AI recommendations or execute decisions.

The W65/W64 next action is reused rather than re-ranked by a new cross-company scoring engine.

## Development

```bash
PYTHONPATH=src python3 -m binario_marketing.cli serve-dev --host 127.0.0.1 --port 8766 --open
```

The repository continues to use exactly the three canonical GitHub workflows.
