# Post-W99 · Contextual Deep Linking

## Objective

Contextual Deep Linking closes the navigation gap between the bounded Today plan and the canonical owner modules. Opening an item should land on the exact locally known record when the Action Center payload already contains a deterministic identifier; it should not merely open a broad module and force the operator to search again.

This layer is navigation-only. It does not become a second task system, does not determine completion, and does not change Action Center priority.

## Position in the development chain

`Portfolio Control Tower → Executive Marketing Cockpit → Today / Operator Execution → Execution Return Flow → Contextual Deep Linking`

- Portfolio decides which company deserves attention first using existing canonical ordering.
- Executive Cockpit explains the selected company.
- Today exposes at most the first five Action Center items without re-ranking.
- Execution Return preserves the operator journey back to Today.
- Contextual Deep Linking narrows the destination from the owner module to the exact record when that record is deterministically identifiable.

## Deterministic target contract

The browser derives a target only from fields already present in the Action Center action payload. No text similarity, fuzzy matching, AI, title matching, date inference, or cross-company search is allowed.

Supported exact mappings:

| Owner view | Evidence | Exact target |
| --- | --- | --- |
| `crm` + `followups` | `entity_id` | CRM activity |
| `crm` + `pipeline` | `opportunity_id` | opportunity |
| `crm` + `contacts` / contact fallback | `contact_id` | contact |
| `calendar` | `entity_id` | publication |
| `commercial-desk` | `lead_id` without CRM contact | lead intake row |
| `commercial-desk` | `lead_id` + `contact_id` | commercial handoff row |
| `campaigns` | `campaign_id` | campaign |
| `execution` | `campaign_id` | campaign execution card |
| `intelligence` | `campaign_id` | campaign intelligence card |
| `content` | `media_id` | company media card |

If those conditions are not met, the result is `OWNER_ONLY`: the owner module may open, but the UI must not claim an exact record was identified.

## Exact focusing without owner duplication

The adapter does not rewrite CRM, calendar, campaign, commercial, execution, intelligence, or content logic. After those modules render their canonical local state, the adapter pairs their rendered rows with the same canonical arrays already used by the owner renderer and adds transient DOM `data-*` anchors.

Examples:

- a rendered CRM follow-up receives the ID of the activity at the same canonical sorted position;
- a pipeline opportunity is anchored within its canonical stage column;
- calendar rows are anchored after applying the same scheduling sort used by the calendar;
- commercial lead and handoff lanes are anchored independently;
- execution/intelligence campaign cards use their canonical campaign IDs;
- content cards use canonical media IDs.

These anchors are browser presentation metadata only. They are not persisted and carry no business semantics.

## Owner state preparation

Before navigation, the adapter may adjust presentation state only when necessary to make the exact record visible:

- CRM selects the canonical tab (`followups`, `pipeline`, or `contacts`).
- Calendar may set the existing `editorialState.selectedId` to the exact publication so the canonical management panel opens when that publication is manageable.
- Campaigns set the existing `campaignState.selectedId`.
- Execution disables `onlyAction` filtering for this explicit navigation.
- Intelligence disables `onlyAttention` filtering for this explicit navigation.

No business object is edited by these presentation changes.

## Visible states

### `FOUND_EXACT`

The exact ID was found in the current owner-module render. The record receives a temporary visual outline and the module shows `PLAN DE HOY · CONTEXTO DE NAVEGACIÓN` with `EXACT TARGET`.

### `TARGET_NOT_FOUND`

The module finished loading, but the exact identifier is not present in its current local render. The layer explicitly states that no substitute was chosen. It does not infer completion, deletion, or equivalence.

### `OWNER_ONLY`

The Action Center action did not provide enough deterministic identity for an exact record. Only the module is opened.

### `LOADING`

The owner module has not finished loading its existing local read model. The adapter waits for the normal owner render callback; it does not poll or issue a second data request.

## Interaction with Execution Return

Execution Return remains the journey authority. Contextual Deep Linking adds no second return bar and no second session task state.

When Execution Return reopens an action, it calls the same wrapped `actionCenterOpen` path, so exact focusing is reconstructed from the destination fields already stored by Execution Return.

When Execution Return is closed or the operator navigates to another owner view, the transient deep-link context and visual highlight are cleared.

## Safety boundary

Contextual Deep Linking:

- performs no `POST`, `PATCH`, `PUT`, or `DELETE`;
- performs no new `fetch` or provider read;
- performs no polling;
- performs no background business work;
- performs no AI or fuzzy matching;
- never calls `.click()` or dispatches a synthetic action;
- never marks a task complete;
- never changes Action Center order;
- never changes CRM/campaign/publication/media business state;
- never crosses company scope.

A visual focus is not completion evidence. Owner modules remain the sole authority for their own mutations and completion semantics.

## Release boundary

This is post-W99 development only. It does not modify the frozen release runtime, release identity, W99 builder, candidate artifact, `main`, or the physical-UAT contract.

`main@60ef38aa01c841c60f98b7dc79fcc9bb5d676e53` remains the frozen W99 source. Physical UAT is still required before any production-ready or release-authority claim.
