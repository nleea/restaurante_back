> Depends on `whatsapp-channel`, `whatsapp-autoreply` and `alert-notifications`.
> Read `docs/messaging/ROADMAP.md` before starting — the commercial model (wholesale buy,
> resell) is what makes the metering a circuit breaker rather than a billing feature.

## 1. Backend — module scaffold and schema

- [x] 1.1 Create `modules/assistant/` (`domain/{entities,ports}`, `application/use_cases`,
      `infrastructure/{llm,models,repositories,api}`)
- [x] 1.2 `AssistantEntitlementModel` (tenant-scoped): plan, enabled, monthly quota units,
      period anchor, warning threshold percent, fallback message
- [x] 1.3 `AssistantUsageLedgerModel` (tenant-scoped, append-only): occurred at, caller kind,
      conversation ref, provider, model, tokens in/out, provider cost, billed units; index
      supporting the period projection
- [x] 1.4 `AssistantConversationStateModel` (tenant-scoped): per-conversation assistant context
- [x] 1.5 Domain entities; register models in `shared/models_registry.py`
- [x] 1.6 Alembic migration `0024_assistant`; run up/down on Postgres
      (salió como **0028_assistant**: 0024–0027 se las llevó `alert-notifications`. up/down/up
      verificados en Postgres; `alembic check` no detecta deriva de las tablas `assistant_*`)
- [x] 1.7 No tenant entitled by default

## 2. Backend — ports

- [x] 2.1 `ConversationEngine` port taking and returning our own dataclasses only
- [x] 2.2 `KnowledgeIndex` port (`retrieve(tenant, query) -> list[Passage]`)
- [x] 2.3 `NullKnowledgeIndex` returning `[]`, mirroring `NullEventPublisher`
- [x] 2.4 Domain errors: `AssistantNotEntitledError`, `RateLimitedError`, `QuotaExhaustedError`,
      `AssistantDisabledError` (kill switch); map to HTTP in `shared/api/errors.py`

## 3. Backend — the metered choke point

- [x] 3.1 One method through which every model call passes:
      `entitlement → kill switch → rate limit → quota → call → ledger`
- [x] 3.2 Rate limit: per-tenant, per-minute, backed by the existing cache; refusal consumes no
      quota
- [x] 3.3 Quota: remaining derived from the ledger for the current period; checked before,
      recorded after
- [x] 3.4 Global kill switch from settings, evaluated before everything else
- [x] 3.5 Per-call ceiling: truncate input to `max_input_tokens`, send `max_output_tokens`
- [x] 3.6 Ledger write on every call, including provider errors that consumed tokens
- [x] 3.7 Composition root exposes only the metered service — verify no wiring reaches the
      engine directly

## 4. Backend — LangChain adapter

- [x] 4.1 `infrastructure/llm/` adapter implementing `ConversationEngine` over LangChain,
      selecting provider and model from the tenant's plan
      (**proveedor: OpenAI**, decidido por el dueño el 2026-07-31. `langchain-openai`; el bucle
      de herramientas vive en el adaptador y tiene tope de vueltas, que es un tope de gasto)
- [x] 4.2 Engine instances cached per plan, not constructed per tenant request
- [x] 4.3 Add the `mypy` module override for `restaurante.modules.assistant.infrastructure.llm.*`
      in `pyproject.toml`, with a comment stating the confinement rule it depends on
- [x] 4.4 Assert by test that no LangChain type appears in `application/` or `domain/`
- [x] 4.5 Add LangChain to `pyproject.toml` dependencies

## 5. Backend — tool registries

- [x] 5.1 Tool abstraction wrapping an existing use case with a schema for the engine
- [x] 5.2 Customer registry: public menu, branch hours, own-order status by phone
      (por CONTACTO de WhatsApp, no por teléfono tecleado: en modo privacidad el número no lo
      sabemos — mismo motivo que `employees.whatsapp_contact_id`. `OrderService.list_orders`
      gana un filtro `whatsapp_contact_id` en vez de una consulta paralela)
- [x] 5.3 Employee registry: built per request by filtering the full tool set through the
      caller's current permissions
- [x] 5.4 Every tool executes under the caller's tenant and permissions — no bypass of the use
      cases' own gates
- [x] 5.5 No tool mutates; ordering and other writes answer with the store link or a handoff

## 6. Backend — conversation flow

- [x] 6.1 WhatsApp path: a `greeted` conversation whose customer opts in moves to `bot`; each
      inbound turn runs the metered call with the customer registry
- [x] 6.2 Admin path: an authenticated employee's question runs the metered call with their
      registry and active branch
- [x] 6.3 History window: send a fixed small number of prior turns (the main input-cost driver)
- [x] 6.4 Consult the knowledge index each turn and answer from tools when it returns nothing
- [x] 6.5 Handoff: an explicit request for a person moves the conversation to `human`
      (se comprueba ANTES de llamar al modelo: quien pide una persona ya decidió que el bot
      no le sirve, y contestarle con el bot es la forma más cara de perderlo)

## 7. Backend — exhaustion and warning

- [x] 7.1 On exhausted quota, send the tenant's configured fallback with the store link
      **without calling the model**
- [x] 7.2 The conversation stays claimable from the shared inbox after a fallback
- [x] 7.3 Register a quota-warning rule with `alert-notifications` so the 80% warning inherits
      its hysteresis
      (implementado como una regla más: `RULE_ASSISTANT_QUOTA` + `AssistantQuotaReader`, la
      misma forma que las otras tres. Un sujeto POR TENANT —la cuota se compra por negocio—;
      el umbral sale del derecho, no del `threshold` de la regla, para no tener dos números
      para lo mismo)
- [x] 7.4 The warning re-arms on a new quota period

## 8. Backend — API, settings, permissions

- [x] 8.1 Admin chat endpoint; usage/quota read endpoint; entitlement management endpoints
- [x] 8.2 Add `assistant.use` and `assistant.manage` to `identity/domain/permissions_catalog.py`
- [x] 8.3 Settings: provider credentials (ours), per-plan model, `max_input_tokens`,
      `max_output_tokens`, rate limit, global kill switch
      (modelo y techos por plan viven en `domain/plans.py`, no en ajustes: son un hecho del
      proveedor con su precio al lado, y separarlos de él es cómo el libro empieza a mentir)
- [x] 8.4 Register the router in the app factory

## 9. Backend — tests

- [x] 9.1 Unentitled tenant: no model call, conversations behave as before
- [x] 9.2 Kill switch blocks every tenant regardless of entitlement, rate and quota
- [x] 9.3 Rate limit refuses within remaining quota and consumes none
- [x] 9.4 Quota refuses within the rate limit
- [x] 9.5 All checks precede the provider call; no unmetered path reaches the engine
- [x] 9.6 Oversized input truncated; output cap sent; overshoot never exceeds one ceiling
- [x] 9.7 Ledger: one entry per call, both cost layers present, immutable, balance derived
- [x] 9.8 Ledger written even when the provider errors after consuming tokens
- [x] 9.9 **Customer registry excludes staff tools**; an injection-style message changes nothing
- [x] 9.10 Employee registry matches permissions; a permission change between turns takes effect
- [x] 9.11 Tenancy never crossed by any tool
- [x] 9.12 Live questions answered by tools even when the index holds similar-looking material
- [x] 9.13 Works with the null index; swapping a populated index changes no use case
- [x] 9.14 Read-only: an order request returns the link; a write request modifies nothing
- [x] 9.15 Exhaustion sends the fallback with **zero** model calls, and the conversation stays
      claimable
- [x] 9.16 Warning alert fires once per period and re-arms on the next
- [x] 9.17 Plan selects the model; no tenant-supplied provider config is honoured
- [x] 9.18 No LangChain type is importable from `application/` or `domain/`

## 10. Frontend — admin chat

- [x] 10.1 Chat panel route and store, showing the branch in scope
- [x] 10.2 States it answers but does not change anything
- [x] 10.3 Hidden with an explanation when the tenant is not entitled
- [x] 10.4 Distinguish a rate-limit refusal ("retry shortly") from an exhausted quota
      ("allowance used up")

## 11. Frontend — usage screen

- [x] 11.1 Usage screen gated on `assistant.manage`: consumption against quota, warning
      threshold, recent breakdown
- [x] 11.2 Past-threshold state is visually unmistakable
- [x] 11.3 Exhausted state explains the customer fallback and that people can still answer

## 12. Frontend — tests

- [x] 12.1 Answers respect the asker's permissions
      (probado en el backend, que es donde vive la frontera: el registro se construye con los
      permisos efectivos de la petición. La pantalla no filtra nada — filtrar en el cliente
      sería fingir una seguridad que no tiene)
- [x] 12.2 Panel hidden and explained without entitlement
- [x] 12.3 Rate limit and exhaustion are distinguishable to the user
- [x] 12.4 Usage screen states and permission gating

## 13. Quality gates

- [x] 13.1 Backend: `ruff`, `mypy --strict`, full `pytest` green — the LangChain override is the
      only one, and scoped to its package
- [x] 13.2 Frontend: lint, type-check, unit tests, production build green
- [ ] 13.3 Manual: entitle one tenant, opt into the assistant from WhatsApp, ask a menu
      question, exhaust the quota and confirm the fallback costs no call
      **NO EJECUTADA.** El change se archivó el 2026-07-31 por decisión del dueño con esta
      tarea pendiente. Queda deliberadamente sin marcar: nadie ha visto todavía el recorrido
      completo contra el despliegue. Para hacerla hacen falta, en este orden: (1)
      `scripts.seed` en cada tenant; (2) contratar el asistente en `/assistant/usage` con
      unidades; (3) encender la oferta en `/whatsapp/autoreply` —requiere que el proceso del
      API haya arrancado con `ASSISTANT_API_KEY` en el entorno—; (4) escribir al número,
      contestar `1` y preguntar.
