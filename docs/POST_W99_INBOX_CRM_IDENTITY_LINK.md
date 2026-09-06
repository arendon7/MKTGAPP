# Post-W99 Inbox → CRM Identity Link

## Purpose

Close the remaining Wave40 operational gap where a Messenger or Instagram actor can be visible in Inbox but cannot be matched to CRM because Meta does not expose a usable `@username`.

This increment does **not** create another CRM, social inbox, priority engine, provider poller, or reply mechanism. It only adds an explicit local association between an observed social actor and an existing company-scoped CRM contact.

## Operator flow

1. Operator opens **Inbox** for one company.
2. Operator explicitly presses **Actualizar desde Meta**.
3. Existing provider read returns recent interactions.
4. If an actor already matches CRM by `@username`, existing Wave39/Wave40 behavior remains.
5. If no username match exists but Meta exposes an actor id, the UI offers **Vincular a CRM**.
6. Operator selects an existing CRM contact.
7. A confirmation explains that the operation is local and does not write to Meta.
8. Server validates the exact refresh-bound HMAC intent and current Inbox evidence.
9. The local social identity link is written.
10. Inbox immediately gains the existing **Abrir CRM** and **Crear seguimiento** actions for that actor.
11. When the exact interaction is present in the current minimized attention snapshot, only its local `crm_contact_id` annotation is patched so Today/Action Center can continue the existing loop without another provider read.

## Privacy contract

The provider person id is transient input only.

Persisted identity evidence contains:
- schema
- company id
- provider namespace
- HMAC-SHA256 fingerprint
- local CRM contact id
- timestamps

It does **not** contain:
- raw Facebook/Instagram person id
- message body
- provider URL
- access token
- refresh intent token
- Meta credential

The fingerprint is keyed with a random 32-byte local identity key. The key is created only when identity linking is actually used and is written with owner-only POSIX permissions (`0600`).

No fingerprint or key is returned to the browser.

## Refresh-bound intent

A link POST cannot be manufactured from only a provider id.

After an explicit Inbox refresh, MERCADEO APP mints an HMAC intent over:

`company + provider + interaction + actor + captured_at`

The token is returned only with the transient Inbox payload. It is never persisted in the attention snapshot or CRM.

The mutation requires:
- current Inbox snapshot state = `CURRENT`
- request `observed_at` exactly equals current snapshot `captured_at`
- valid HMAC intent for the same company/provider/interaction/actor/refresh

If Inbox was refreshed in between, the mutation fails with HTTP 409 and the operator must use the new evidence.

## Link authority and replacement

An explicit human identity link is stronger evidence than automatic username matching.

If a later `@username` match points to a different CRM contact:
- the explicit link remains the CRM authority;
- Inbox exposes `LINKED_USERNAME_MISMATCH`;
- the UI explains the disagreement;
- the operator can explicitly change the link.

Replacement is optimistic and fail-closed:
- current contact id must match `expected_contact_id`;
- `replace_confirmed=true` is mandatory when changing contacts;
- stale or different local state returns conflict;
- no heuristic reassignment occurs.

A missing/deleted linked CRM contact is reported as `BROKEN` and can be explicitly repaired.

## Provider boundary

The link route performs **zero provider I/O**.

It does not:
- call Meta Graph API;
- send a message;
- reply to a comment;
- refresh Inbox;
- poll provider state;
- hide/delete/moderate anything;
- create an automatic CRM contact.

The only Meta read remains the existing explicit Inbox refresh.

## CRM boundary

Links can target only an existing contact belonging to the same company.

The CRM schema is unchanged. Raw provider identity is never copied into:
- contact notes;
- Instagram field;
- tags;
- activities;
- opportunities.

Follow-up creation remains the existing Wave40 explicit action and uses the existing interaction marker deduplication.

## Action Center / Today

No second priority engine is introduced.

The current minimized Inbox snapshot already supports `crm_contact_id`. After a successful link, the exact current interaction can be locally annotated with the selected CRM contact id. This does not alter provider facts or trigger a provider read.

Future explicit refreshes resolve the identity link before snapshot minimization, so the CRM contact flows naturally into the existing Inbox Attention → Action Center → Today path.

## macOS development bundle

The isolated bundle remains:

`Binario Marketing IA Post-W99 Dev.app`

It packages:
- `inbox_crm_identity.py`
- `service_post_w99_inbox_crm_identity_app.py`
- `inbox-crm-identity.js`

Audit asserts HMAC usage, `0600`, zero MetaGraph authority in the new terminal, and no browser polling.

Smoke only GETs the browser asset. It does not refresh Meta or create an identity key/link.

## Explicit non-authority

This increment has no authority to:
- modify frozen W99 `main`;
- certify physical Apple Silicon UAT;
- create W100;
- publish a GitHub release;
- add a fourth GitHub workflow;
- deploy cloud infrastructure;
- add background provider polling.

Canonical frozen `main` remains:

`60ef38aa01c841c60f98b7dc79fcc9bb5d676e53`
