# Post-W99 · Company Onboarding / Readiness Portfolio

## Release boundary

Canonical `main` remains frozen at W99 commit `60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` while the physical Apple Silicon UAT remains open. This increment belongs only to `dev/post-w99-action-center` through a feature PR. It does not create release, production, tag, or publication authority.

## Goal

Turn **Empresas** into a practical multi-company onboarding surface: for every brand, show what is ready, what is missing, and the next owner action without creating a second setup/readiness engine.

## Authority model

W50 Marketing Command Center remains the readiness authority. Its existing eight steps are reused exactly:

1. Workspace de creación
2. Conexión Meta
3. Facebook Page
4. Instagram profesional
5. Cuenta publicitaria
6. Campaña de marketing
7. Creative Studio
8. CRM con contactos

`GET /api/portfolio/companies` composes the existing company-scoped W50 state and minimizes it to company identity, readiness steps, completion percentage, and next owner action.

All mutations remain in their existing company-scoped owner modules. The portfolio does not create or edit companies, credentials, Meta associations, campaigns, creatives, or CRM data.

## Meta safety

W50 `marketing_command_center()` uses local credential/status and persisted company associations and explicitly performs **no Meta remote readback**.

The portfolio browser adapter prevents the historical Companies view from calling Meta discovery while **Todas las empresas** is selected. Provider discovery remains available only after entering a concrete company, where the existing company setup surface retains authority.

The portfolio serializes no credential, token, Facebook Page ID, Instagram ID, Ad Account ID, provider remote ID, or remote asset collection.

## Browser behavior

When `Empresas` is opened with no company selected:

- show an aggregate readiness summary;
- show one card per company;
- show the W50 readiness steps and percentage;
- route `Ir` to the exact company and existing owner view;
- expose `+ Nueva empresa` by returning to the existing company creation form;
- refresh only local state.

When a concrete company is selected, the existing owner Companies/Meta UI is preserved and a `Ver todas las empresas` return action is added.

## Development runtime

```bash
PYTHONPATH=src python3 -m binario_marketing.cli serve-dev --host 127.0.0.1 --port 8766 --open
```

`serve-dev` terminates in `service_post_w99_portfolio_companies_app`. Canonical `serve` remains unchanged.

## CI contract

The repository must continue to contain exactly these three workflows:

- `ci.yml`
- `full-mac-app.yml`
- `persistent-release.yml`

Merge is allowed only after Canonical Source CI, Full Mac App arm64 iteration, and Persistent Mac Release certify the exact feature head successfully.
