# Wave 49 · Creative Studio

Wave 49 closes the product gap between Video Studio, the company library, campaigns, organic distribution and Paid Media.

## Product flow

The canonical creative path is now:

1. **Create / import**
   - import image/video into the company library; or
   - create and render inside the company's canonical Video Studio workspace.
2. **Promote render**
   - a completed `PASS` render can be explicitly sent to Creative Studio;
   - promotion is content-addressed by SHA-256, so repeating the action reuses an existing matching company asset instead of duplicating it.
3. **Creative brief**
   - title;
   - workflow stage;
   - marketing purpose;
   - linked campaign;
   - intended channels;
   - primary copy + headline;
   - CTA + destination;
   - optional public media URL for organic images;
   - publication date;
   - notes / hypothesis.
4. **Campaign**
   - linking a creative to a company campaign also links the managed media into that campaign.
5. **Organic distribution**
   - video: eligible company media can become a local Reel draft/scheduled item;
   - image: organic Meta publishing still requires an explicit public HTTPS media URL in this gate;
   - when `publish_at` is present, the explicit prepare action creates a queued scheduled publication; otherwise it creates a draft.
6. **Paid Media**
   - managed images can be sent to the Wave 48 Paid Media Center;
   - campaign, copy, CTA, destination and managed image are prefilled;
   - the paid-media draft is linked back to the creative item;
   - Wave 48 safety remains unchanged: remote hierarchy creation is PAUSED only.

## State model

`CreativeStore` is additive metadata around `CompanyMedia`. It never owns media bytes.

Schema: `binario.marketing.creative-item.v1`

Stages:
- `BRIEF`
- `DRAFT`
- `READY`
- `SCHEDULED`
- `PUBLISHED`
- `PAID`
- `ARCHIVED`

The API also reports `UNPROFILED` for company media that has not yet received a creative brief.

The displayed effective stage is reconciled with linked publications and paid-media plans so a queued publication reads as `SCHEDULED`, a confirmed remote publication as `PUBLISHED`, and a linked paid plan as `PAID`.

## Endpoints

- `GET /api/companies/{company_id}/creatives`
- `GET /api/companies/{company_id}/creatives/context`
- `PATCH /api/companies/{company_id}/creatives/{media_id}`
- `POST /api/companies/{company_id}/creatives/{media_id}/publication`
- `POST /api/companies/{company_id}/workspace/renders/{render_id}/promote`

Paid Media continues using the existing Wave 48 company endpoints. Wave 49 automatically links a managed-image paid plan back to its Creative Studio item when that media has a saved creative profile.

## Safety boundaries

Wave 49 does **not** introduce a direct remote publish-now action, ad activation, automatic spend, provider polling or hidden provider mutation.

The only scheduling transition is caused by an explicit user action that prepares a publication with a specified `publish_at`. Existing scheduler semantics then apply at the requested date.

Paid Media still creates Campaign / Ad Set / Ad only in `PAUSED` through Wave 48.

## macOS iteration

`build_full_mac_current.sh` remains arm64-only and now layers:
- Wave 47 product shell;
- Wave 48 Paid Media Center;
- Wave 49 Creative Studio.

The current build must pass Wave 47, Wave 48 and Wave 49 bundle audits before the `.app` is accepted as an iteration candidate.
