# Design: kds-components-recipes-realtime

## Context

`wire-kds-to-kitchen` (archived 2026-07-01) put the KDS UI in production at `/kitchen` on real
tickets, deliberately deferring three things to backend work. Investigation before this change
established the current state:

- **Routing already fans out**: `route_order` creates one ticket per `(order_item × mapped
  station)` with the mapping's `role` denormalized onto the ticket
  (`kitchen/application/use_cases/manage_kitchen.py:159-180`). `product_stations` is unique on
  `(product_id, kitchen_station_id)`, so N stations per product is a config concern, not a
  schema change. Idempotency is app-level `ticket_exists` check-then-insert with **no DB unique
  constraint** behind it (`kitchen/infrastructure/models.py` — `OrderItemStationModel`).
- **Recipes are BOM-only**: `RecipeItemModel` (variant → ingredient, quantity, unit) and
  `IngredientModel` (name, unit). No steps, no allergens anywhere in the codebase; responses
  carry ingredient ids, not names.
- **No push infra**: zero websocket/SSE code; `redis ^5.0` installed but used only as an
  optional cache backend (`shared/config.py:46-48`); ticket mutations emit no events — the only
  side effect is the in-process `_emit_kitchen_state` push to orders.
- Frontend seams from the previous change: `lib/kds/adapter.ts` (tickets → KDS model),
  `RECIPES_ENABLED` flag in `useKdsBoard.ts`, store polling (`startPolling`, 10 s).

Both backend modules follow the same layered layout (domain/application/infrastructure with
`api/router.py`, `deps.py`, `schemas.py`); permissions are enforced with
`require_permission("<module>.<action>")`; migrations are sequential files under
`backend/migrations/versions` (latest: `0004_kitchen_roles_and_ready_rollup.py`).

## Goals / Non-Goals

**Goals:**

- A dish routed to N stations renders as **one docket item with N role-named components**; the
  "waiting on station X / getting cold" alert layer works across a dish's stations.
- The recipe drawer works on real data: ingredients (name, quantity, unit), preparation steps,
  allergens — editable via API, readable in one call from the KDS.
- Ticket creation/advance reaches open boards in ~1 s via SSE over Redis pub/sub (multi-worker
  safe); polling stays as a degraded-mode fallback.
- DB-enforced ticket uniqueness per `(order_item_id, kitchen_station_id)`.

**Non-Goals:**

- No recipe authoring UI in this change (steps/allergens are written via API/scripts; a menu
  screen for them is a future frontend change).
- No per-item cook notes or addon/modifier display (order items carry no notes field; addons
  are a separate follow-up).
- No un-advance/recall; no printing; no SLA metrics.
- No WebSocket (SSE is one-directional and enough — the board only listens).

## Decisions

### D1 — Components come from ticket grouping, not a new backend concept

The adapter groups tickets by `order_item_id`: one `KdsItem` per order item, one `KdsComponent`
per ticket, component name = `ticket.role`, falling back to the station label when role is null.
Item qty/label come from the existing item index. No backend "component" table.
*Alternative rejected:* a sub-ticket/component entity server-side — routing fan-out + role
already encodes exactly this; a new entity would duplicate state and require migrating existing
tickets.

Consequences handled in the adapter: `startedAt` stays the min `entered_at` across the order;
an item's status/progress derive from its components via the existing `logic.ts` (untouched);
solo unresolvable tickets keep degrading to their own docket entry.

### D2 — Ticket uniqueness enforced by the database

Alembic migration adds a unique constraint on `order_item_stations (order_item_id,
kitchen_station_id)` (tenant-scoped rows already; the pair is globally unique since ids are
uuids). `create_ticket` catches the integrity error and treats it as "already routed" so
concurrent double-routes converge instead of duplicating. The app-level `ticket_exists` check
stays as the fast path.

### D3 — Recipe details as a new table, keyed by product variant

New `recipe_details` table (module `recipes`): `id`, tenant/branch mixins as per module
convention, `product_variant_id` (FK, **unique** — one detail row per variant), `steps`
(JSON array of strings, ordered), `allergens` (JSON array of enum strings
`gluten|dairy|nuts|shellfish|vegan`, validated in the schema layer), `photo_label` (nullable
string). Endpoints (prefix `/recipes`, permissions `recipes.read`/`recipes.update` following the
module's existing codes):

- `PUT /recipes/variants/{variant_id}/details` — upsert steps/allergens/photo_label.
- `GET /recipes/variants/{variant_id}/details` — raw details (404 when none).
- `GET /recipes/variants/{variant_id}/card` — the KDS read model: `{ ingredients: [{name,
  quantity, unit}], steps, allergens, photo_label }`, joining BOM lines with ingredient and
  unit names server-side. Returns an empty-ingredients card when the variant has details but no
  BOM, and 404 only when the variant has neither.

*Alternative rejected:* columns on `RecipeItemModel` (BOM lines are per-ingredient — steps are
per-dish); a separate steps table with one row per step (overkill; steps are an ordered text
list, JSON keeps the API and migration simple).

### D4 — Realtime: Redis pub/sub + SSE, fetch-stream client

- **Publish**: a small `KitchenEventPublisher` port in the kitchen module; implementation
  publishes JSON (`{type: "ticket_created"|"ticket_advanced", branch_id, station_id, order_id?,
  ticket_id, status}`) to Redis channel `kds:{tenant_id}:{branch_id}` using the existing
  `redis_url` setting. Called (best-effort, non-blocking — failures logged, never break the
  mutation) from `route_order` and `advance_ticket`.
- **Stream**: `GET /kitchen/events?branch_id=` in the kitchen router, gated by `kitchen.read`,
  returns `StreamingResponse` (`text/event-stream`) subscribing to that channel; heartbeat
  comment every ~15 s so proxies keep the connection; client disconnect ends the subscription.
- **Frontend client**: EventSource cannot send `Authorization`, so a small fetch-stream SSE
  reader (`lib/sse.ts`) uses `fetch` with the Bearer header and parses `data:` lines. The
  kitchen store starts it with polling: on any kitchen event → debounce ~300 ms → refetch the
  affected station (or all on `ticket_created`); while the stream is healthy, polling relaxes to
  60 s (pure fallback); on stream error → reconnect with backoff and restore 10 s polling.
- **Degraded mode**: if Redis is unreachable the publisher no-ops and `/kitchen/events` still
  serves heartbeats; the board silently lives on polling. Redis is required only for push to
  actually deliver.

*Alternatives rejected:* in-memory pub/sub (breaks with >1 uvicorn worker — user chose
multi-worker-ready); WebSocket (bidirectional machinery for a listen-only screen); token in the
SSE query string (leaks the JWT into logs; fetch-stream keeps it in headers).

## Risks / Trade-offs

- [Existing dishes mapped to one station render as one component — looks like phase 1] →
  correct behavior; the split appears as soon as products are mapped to multiple stations with
  roles. Seed/demo data should map a few products to 2-3 stations to make the feature visible.
- [Duplicate tickets may already exist, blocking the unique constraint migration] → migration
  first deletes exact duplicates keeping the most advanced/oldest ticket, then adds the
  constraint.
- [SSE connections held open per board × worker] → boards are few (wall screens); heartbeat +
  client reconnect bound leaked connections; no fan-in state kept server-side beyond the Redis
  subscription.
- [JSON columns for steps/allergens skip DB-level enum enforcement] → validated in Pydantic
  schemas on write; the read model re-filters unknown keys so the frontend enum stays closed.
- [Recipe card joins BOM + ingredients + units per open] → drawer opens are rare and per-dish;
  one aggregated query, no N+1.
- [Axios interceptors (401 refresh) don't cover the fetch-stream client] → the SSE client takes
  the current access token per (re)connect and treats 401 as a reconnect-after-refresh signal
  via the auth store.

## Migration Plan

1. Backend: migration `0005_recipe_details.py` (new table) and `0006_ticket_station_unique.py`
   (dedupe + unique constraint); both `alembic upgrade head` on deploy, no data backfill needed.
2. Deploy backend (publisher no-ops if Redis is absent — safe before Redis is provisioned).
3. Frontend ships adapter grouping + drawer + SSE client; fully backward compatible with a
   backend that hasn't restarted yet (polling still drives the board).
4. Map pilot products to multiple stations with roles; author steps/allergens for top dishes.
5. Rollback: revert frontend commit (board returns to 1-ticket-1-component + polling); backend
   endpoints/events are additive and can stay.

## Open Questions

- Exact `recipes` permission codes to reuse (`recipes.read`/`recipes.update` vs `menu.*`) —
  confirm against the module's existing router during implementation and follow suit.
