# Wave 51 · AI Copilot Core

Wave 51 makes AI a transversal **analysis and drafting** layer over BINARIO Marketing. It is intentionally not an autonomous marketing executor.

## Providers

The Copilot has provider-neutral adapters for:
- OpenAI Responses API;
- Anthropic Messages API;
- Google Gemini `generateContent`;
- Ollama local chat API.

BINARIO does not pin a cloud model name in product code. Each company explicitly chooses provider and model so model lifecycle changes do not silently change the product contract.

## Credentials

Cloud keys resolve in this order:
1. provider environment variable (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`);
2. macOS Keychain through the native BINARIO helper.

The existing Meta Keychain helper was generalized into namespaced slots while retaining `meta` as the default namespace, preserving compatibility with the existing `MetaCredentialStore` invocation.

Namespaces:
- `meta`
- `openai`
- `anthropic`
- `gemini`

Ollama requires no cloud API key.

API keys are never persisted in project/company/AI session JSON. Environment-controlled credentials cannot be overwritten or deleted from the application.

## Explicit company configuration

Each company stores only non-secret AI settings:
- provider;
- model;
- response language;
- brand/voice guidance.

Schema: `binario.marketing.ai-settings.v1`.

## Tasks

Wave 51 exposes three user-triggered tasks:
- `STRATEGY`: diagnose company marketing state and propose highest-leverage next actions;
- `CAMPAIGN`: improve one explicitly selected company campaign;
- `CREATIVE`: improve one explicitly selected Creative Studio item and return creative variants.

Campaign and Creative tasks fail closed unless the entity is explicitly selected and belongs to the active company.

## Sanitized context

Before a provider request, BINARIO constructs `binario.marketing.ai-context.v1` from local company state.

Included:
- company name;
- operational readiness and missing setup labels;
- aggregate flow/attention counts;
- aggregate CRM counts;
- local paid-media/publication summaries;
- campaign names/objectives/status/channels/counts/notes;
- creative workflow summaries;
- the explicitly selected campaign or creative brief when applicable.

Explicitly excluded:
- CRM contact records, names, emails, phones and WhatsApp numbers;
- media/image/video bytes;
- provider credentials or Meta tokens;
- remote provider refresh performed implicitly by the Copilot.

The provider receives the resulting sanitized JSON context plus the user's optional instruction.

## Structured output

Every adapter is normalized to one application contract:
- summary;
- diagnosis;
- recommendations with priority/area/next step;
- creative variants with copy/headline/CTA;
- campaign brief with objective/audience/proposition/channels/KPIs/notes.

OpenAI uses a strict JSON schema in the Responses request. Other providers are instructed/requested to return JSON and pass through the same local normalization/limits before persistence.

## Provenance

Every successful generation creates an immutable local session:

Schema: `binario.marketing.ai-session.v1`.

Stored fields include:
- provider and model;
- task;
- selected campaign/creative ids;
- optional user instruction;
- SHA-256 of the canonical sanitized context;
- the exact sanitized context snapshot;
- normalized output;
- non-secret provider response metadata;
- timestamp.

Secret-like keys are stripped from provider metadata before persistence.

## Human-in-the-loop execution lock

The AI provider receives **no marketing tools/function calls**.

Wave 51 does not let AI:
- publish or schedule social content;
- reply to comments/messages;
- create or activate Meta Ads hierarchy;
- spend budget;
- refresh remote analytics/inbox automatically;
- mutate CRM or campaign state automatically.

A user can explicitly choose `Usar en Creative Studio` for a generated creative variant. That action only updates the **local creative brief** (copy/headline/CTA and stage `DRAFT`) after confirmation. It performs no remote provider action.

## Provider disclosure

The UI discloses before generation that sanitized marketing context will be sent to the selected external provider. Generation requires an explicit user click and confirmation.

For Ollama, the request is sent only to `127.0.0.1:11434`.

## macOS iteration

`build_full_mac_current.sh` remains arm64-only and now layers Wave 47 → 48 → 49 → 50 → 51, followed by all product audits.

The compiled native Keychain helper remains inside the app bundle and defaults to the historical Meta namespace when called without a second argument.
