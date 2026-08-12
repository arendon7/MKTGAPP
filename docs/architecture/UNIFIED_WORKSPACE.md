# Unified Workspace reconstruction

This layer reconstructs the later documented R22 orchestration contracts without claiming byte-identical recovery.

## Contracts

- Workspace project registry shared by all apps.
- Project/Handoff Center for transitions between apps.
- Evidence Registry.
- Artifact Registry.
- Decision Registry.
- Unified Timeline.
- Optional AI Gateway with usage ledger.

Registries are append-only SHA-256 hash chains so accidental or manual history edits are detectable. AI requests receive explicit context capsules and usage is logged; the gateway does not write canonical project memory.

This shared layer is intentionally app-agnostic so Apps 01–12 adopt the same project/evidence contracts rather than duplicating state.
