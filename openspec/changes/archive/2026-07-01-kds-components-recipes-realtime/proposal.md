# Proposal: kds-components-recipes-realtime

## Why

The KDS at `/kitchen` runs on real data since `wire-kds-to-kitchen`, but three of its designed
features are dormant because the backend doesn't feed them: the dish→component split (the UI's
headline feature) renders one component per dish, the recipe drawer is hidden for lack of a data
source, and the board only knows about changes when it polls. Investigation showed the component
split is *already* half-built server-side — routing fans out one ticket per mapped station with a
`role` — so this change finishes the picture: group those tickets as components, give recipes a
real source (steps + allergens), and push ticket changes live over SSE.

## What Changes

- **Components (mostly frontend)**: the KDS adapter groups tickets by `order_item_id` — one dish
  with N components (one per routed station), component name = the ticket's `role`, falling back
  to the station label. Backend hardening: a DB unique constraint on
  `(order_item_id, kitchen_station_id)` so routing idempotency stops being a race-prone
  check-then-insert.
- **Recipes (backend + frontend)**: new per-variant recipe details — preparation steps and
  allergens (`gluten|dairy|nuts|shellfish|vegan`) — with CRUD endpoints, plus an aggregated
  "recipe card" read endpoint for the KDS (ingredients with resolved names/quantities/units +
  steps + allergens in one call). The KDS recipe drawer turns back on, loading the card on open.
- **Realtime (backend + frontend)**: kitchen ticket mutations (`route_order`, `advance_ticket`)
  publish events to a per-tenant/branch Redis pub/sub channel; a new `GET /kitchen/events` SSE
  endpoint streams them (gated by `kitchen.read`). The board subscribes on mount using a
  fetch-stream client (EventSource can't send the Bearer header) and refreshes on events;
  existing polling remains as fallback at a relaxed cadence while the stream is healthy.
- Redis becomes a runtime dependency of the kitchen realtime path (it is already an installed
  dependency, used today only as optional cache backend).

## Capabilities

### New Capabilities

_None — all three streams extend existing capabilities._

### Modified Capabilities

- `kitchen-management`: ticket-change events published on route/advance; SSE stream endpoint;
  DB-enforced ticket uniqueness per (order_item, station).
- `recipes-management`: recipe details (steps, allergens) per product variant with CRUD; an
  aggregated recipe-card read model for kitchen screens.
- `frontend-kitchen`: dockets show one dish with N station components (role-named); recipe drawer
  enabled and fed by the recipe card endpoint; board updates live via SSE with polling fallback.

## Impact

- **Backend**: `modules/kitchen` (event publishing in `manage_kitchen.py` route/advance paths,
  SSE router endpoint, unique-constraint migration on `order_item_stations`), `modules/recipes`
  (new recipe-details model + Alembic migration, CRUD + recipe-card endpoints, schemas),
  `shared` (a small pub/sub abstraction over the existing redis dependency).
- **Frontend**: `lib/kds/adapter.ts` (group by order_item), `services/recipes.api.ts` (new),
  `services/kitchen.api.ts` + a fetch-stream SSE client, `stores/kitchen.ts` (event-driven
  refresh + relaxed polling), `components/kds/KdsRecipeDrawer.vue` + `useKdsBoard.ts`
  (`RECIPES_ENABLED` on, async recipe load), KDS item row (role-named components).
- **Ops**: kitchen realtime requires a reachable Redis (`cache` settings already carry the URL);
  degraded mode without Redis = no push, polling continues to work.
- **No breaking API changes**; existing endpoints untouched.
