## Why

After the first three changes, WhatsApp answers instantly, confirms orders, tracks deliveries
and warns staff — all without a model. What is left is the part that genuinely needs one:
**understanding a question nobody scripted.** A customer asking "¿tienen algo sin cebolla?" or
"¿a qué hora cierran hoy?"; an owner asking "¿cuánto vendimos ayer?" or "¿qué se está acabando?".

This change adds that, and it adds the machinery that makes it survivable as a business.
Because tokens are bought wholesale and resold (see `docs/messaging/ROADMAP.md`), **it is our
money that burns**, which makes the metering not a billing feature but a circuit breaker.

Two convictions from the exploration shape the whole design:

- **Do not ask the index what the database knows.** Live state — stock, sales, orders, the
  menu, hours — is answered by calling existing use cases as tools, never by retrieval.
  Embedding a report produces a bot that confidently states last week's numbers.
- **The model never gets a credential; it gets a caller's context.** A customer's tool
  registry physically does not contain the sales report. An employee's registry is exactly
  their permissions. Prompt injection is defended by capability, not by wording.

## What Changes

- **`AssistantService` as a driving adapter, not a domain.** WhatsApp and an admin chat both
  enter through it; it calls the same use cases the REST API calls, under the same tenancy,
  RBAC and audit.
- **`ConversationEngine` port with a LangChain adapter.** LangChain lives only in
  `infrastructure/llm/` — chosen because provider choice (Claude or OpenAI) is our margin
  lever, not a tenant preference. Nothing from it crosses into `application/` or `domain/`.
- **`KnowledgeIndex` port with a null adapter.** No corpus exists yet, so retrieval returns
  nothing and the assistant answers from tools. When prose exists, a pgvector adapter is
  swapped in without touching a use case. Same shape as the existing `NullEventPublisher`.
- **Two tool registries, by caller.** A WhatsApp customer gets menu, hours and order status. An
  authenticated employee gets tools filtered to their own permissions — a waiter asking for
  the finance report is refused because the tool is not there and the gate would fail anyway.
- **Read-only in this change.** No tool mutates. Conversational order taking arrives later
  with `ConversationCart`; the assistant's answer to "quiero pedir" is the store link.
- **One choke point for every model call**: `entitlement → rate limit → quota → call →
  ledger`. If there are two paths, one of them is free.
- **Three distinct limits.** Quota is monthly and commercial; the rate limit is per-minute and
  defensive; the kill switch is global and ours. One mechanism cannot serve all three.
- **A per-call cost ceiling.** Input is truncated and output is capped, so the maximum cost of
  a single call is known in advance and the quota's overshoot is a computable number rather
  than a hope.
- **An append-only, two-layer usage ledger**: what the provider cost us and what the tenant was
  billed, per call. Without both, an unprofitable tenant is invisible.
- **Graceful exhaustion.** At 80% the owner is warned — as an alert on the existing rule
  machinery, with its hysteresis. At 100% the assistant degrades to a static message with the
  store link, sent **without calling the model**, and the conversation stays available for a
  human.

Out of scope: RAG with a real corpus, conversational order taking, any write tool, and voice or
image input.

## Capabilities

### Added Capabilities
- `assistant-core`: a conversation engine behind a port with a LangChain adapter and a null
  knowledge index; per-caller tool registries built from existing use cases and bounded by the
  caller's permissions; a single metered choke point enforcing entitlement, a per-minute rate
  limit, a monthly quota and a global kill switch; a per-call token ceiling making the maximum
  cost knowable in advance; an append-only two-layer usage ledger; degradation to a
  model-free fallback message on exhaustion; a quota-warning rule registered on the alert
  machinery.
- `frontend-assistant`: an admin chat panel that answers within the signed-in user's
  permissions, and a usage screen showing consumption against the quota with its warning
  threshold.

## Impact

- **Backend**: new `modules/assistant/` with `domain/{entities,ports}`,
  `application/use_cases`, `infrastructure/{llm,models,repositories,api}`; migration adding
  entitlement, quota period and the usage ledger.
- **New dependency**: LangChain, confined to `infrastructure/llm/`. It is not typed for
  `mypy --strict`, so that package needs a module-level override — honest only because nothing
  from it escapes the adapter.
- **New settings**: provider credentials (ours, not per tenant), default model per plan,
  per-call input/output ceilings, global kill switch.
- **Cross-module reads**: the assistant calls menu, hours, orders, inventory and reporting use
  cases as tools; it registers a rule with `alert-notifications` and sends through the
  messaging gateway. All outbound arrows.
- **Financial exposure**: a runaway loop spends our money. The rate limit and the per-call
  ceiling bound it; the kill switch stops it.
- **Operational**: token spend becomes a live cost line that needs watching from day one.
- **Not breaking**: with no tenant entitled, no model call is ever made and every earlier
  change behaves identically.
