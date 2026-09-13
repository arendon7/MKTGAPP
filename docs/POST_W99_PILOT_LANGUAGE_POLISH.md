# Post-W99 Pilot Language Polish

## Boundary

This increment belongs only to the post-W99 development chain. Canonical `main` remains frozen at:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`

This is pilot presentation work and **not production readiness**, release authority or physical UAT evidence.

## Purpose

The cumulative pilot already has the required operational authorities, navigation, company readiness guidance, passive journey evidence, data snapshots and local session status. The remaining presentation problem is that some operator-facing surfaces still expose engineering vocabulary inherited from those certified layers.

The pilot language adapter makes the current `serve-dev` experience read like MERCADEO APP without renaming internal schemas, modules, routes, events, waves or historical implementation files.

## Presentation-only changes

The adapter applies operator-facing terminology such as:

- `Inbox` -> `Mensajes` in primary navigation;
- `Cockpit` -> `Panel ejecutivo`;
- `Action Center` -> `Centro de acciones`;
- `stores` -> `fuentes de datos`;
- `snapshot` -> `respaldo` / `copia local` where displayed to the operator;
- W50/readiness engineering prose -> `preparación de la empresa`;
- `PASS` -> `VERIFICADO` in the visual journey diagnostic;
- technical multi-company action codes -> `Siguiente acción recomendada`.

The canonical route names, internal state values and evidence statuses are unchanged.

## Authority preservation

W50 remains the authoritative company readiness engine. The adapter does not copy, calculate or mutate readiness. It changes only visible DOM text after existing renderers have produced their normal output.

Pilot Journey remains the source of passive navigation evidence. Pilot Data Safety remains the snapshot authority. Pilot Session Status remains the local health/readability projection.

## Safety

`web/pilot-language-polish.js` has:

- no API calls;
- no provider reads;
- no provider mutations;
- no POST/PATCH/DELETE;
- no publishing;
- no campaign activation;
- no CRM mutation;
- no AI execution;
- no localStorage writes;
- no automatic navigation;
- no background polling;
- no `MutationObserver`.

It reacts only to already-existing render/bootstrap events and explicit clicks, using bounded `setTimeout` calls to polish text after known UI updates.

## Error presentation

The pilot bootstrap failure surface no longer exposes a raw technical exception to the primary operator view. The operator receives a product-facing recovery instruction; detailed diagnostics remain a development concern rather than normal pilot copy.

## Runtime chain

The cumulative dev terminal becomes:

`service_post_w99_pilot_language_polish_app`

which extends:

`service_post_w99_pilot_session_status_app`

The canonical release `serve` path is unchanged. The repository continues to use exactly the three canonical workflows:

- `.github/workflows/ci.yml`
- `.github/workflows/full-mac-app.yml`
- `.github/workflows/persistent-release.yml`

No release tag, GitHub Release, production claim, provider authority or physical UAT authority is introduced.
