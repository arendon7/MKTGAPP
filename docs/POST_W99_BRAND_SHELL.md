# Post-W99 Brand Shell & Favicon

## Purpose

This increment removes the remaining legacy BINARIO identity from the **first HTML response** of the post-W99 development experience and gives MERCADEO APP a real local favicon.

It is a **presentation-only** adapter. It is **not production readiness**, does not change any business module, and grants no provider, publication, scheduling, restore, release, tag, or deployment authority.

Frozen `main` remains exactly:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

Development integration remains on `dev/post-w99-action-center` only.

## Problem removed

The historical `web/index.html` still contains the original bootstrap identity:

- `BINARIO Marketing` in the document title;
- `SISTEMA BINARIO` in the initial topbar;
- `Marketing Workspace` as the initial heading;
- no favicon declaration.

#190 later corrects the visible title and labels with JavaScript, but that happens after the browser has already received and begun rendering the HTML. This can expose the old tab title during first paint and gives the browser no canonical icon to request.

## First-response branding

`service_post_w99_brand_shell_app.py` extends the cumulative #196 terminal and intercepts only the root document request (`GET /`).

Before any HTML bytes are sent it applies a bounded transformation:

- title → `MERCADEO APP · Centro de operaciones`;
- application name → `MERCADEO APP`;
- description → `Centro local multiempresa para operaciones de marketing.`;
- theme color → `#171717`;
- favicon → `/mercadeo-app-icon.svg`;
- topbar eyebrow → `MERCADEO APP`;
- topbar heading → `Centro de operaciones`.

The transformation is fail-closed. If the expected historical source contract changes, the adapter refuses to silently serve a partially transformed shell.

The historical `web/index.html` remains untouched and auditable. The browser nevertheless receives MERCADEO APP identity from the **first HTML response**, rather than waiting for a later DOM patch.

## Favicon

`web/mercadeo-app-icon.svg` is a deliberately minimal local icon:

- 64×64 SVG viewBox;
- dark rounded tile;
- white geometric `M` mark;
- accessible `<title>MERCADEO APP</title>`;
- no remote images, fonts, scripts, URLs, data URIs, or network dependencies.

The development terminal serves the same local asset at:

- `/mercadeo-app-icon.svg` — canonical link target;
- `/favicon.ico` — compatibility response for browsers that probe the conventional path.

No additional brand system or alternative logo authority is introduced by this increment.

## Compatibility with #190

`web/pilot-language-polish.js` remains in the cumulative chain. Its idempotent MERCADEO APP title/label normalization is retained as a compatibility layer for later dynamic UI renders.

#197 simply ensures that the browser no longer needs to wait for that JavaScript to see the correct product identity initially.

## Authority boundaries

This increment adds no:

- business API;
- POST, PATCH, PUT, or DELETE handler;
- Meta, Facebook, Instagram, ads, or other provider read/write;
- AI provider call;
- CRM, Inbox, campaign, content, calendar, scheduler, publication, or paid-media mutation;
- snapshot creation, restore, or delete;
- polling, worker, or background task;
- release, tag, deployment, or production authority.

It reads only the repository's local HTML/SVG presentation files.

## Release boundary

The repository continues to use exactly these three canonical workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

Only `serve-dev` advances to this terminal. Canonical release `serve`, the W99 physical UAT route, and frozen `main` remain separate.
