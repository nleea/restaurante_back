# Proposal: kitchen-station-task-lists

## Why

A station's component on the KDS shows a single label (the mapping's `role`, or the station
name), which reads too generic: the grill owes the burger *two* things — the patty **and** the
smoked bacon — and the cook can't see that breakdown. Kitchens need each station's work spelled
out per dish, itemized and readable, without changing how work is checked off (one status per
station is right: the grill marches its whole part at once).

## What Changes

- Product→station mappings gain an ordered **task list** (e.g. Parrilla → ["Carne de
  hamburguesa", "Tocineta ahumada"]) alongside the existing `role`. Editable via a new mapping
  update endpoint; still one mapping per (product, station).
- Routing copies the mapping's tasks onto the ticket at fire time (frozen, like `role` today):
  editing the config later never rewrites tickets already on the line.
- The KDS renders each component's tasks as read-only sub-lines — in the docket's component rows
  and in the my-station list — while status, timers, alerts and tap-to-advance stay **per
  station** (one ticket per station, unchanged).
- The Configuración form edits the task list per mapping (and can now also fix a mapping's role
  without detach/re-attach).
- **No changes** to ticket granularity, unique constraints, routing fan-out, statuses, or the
  recipes module (the recipe drawer remains the "how"; tasks are the "what").

## Capabilities

### New Capabilities

_None — this refines existing kitchen capabilities._

### Modified Capabilities

- `kitchen-management`: product→station mappings carry an editable task list; routing
  denormalizes tasks onto tickets; a mapping update operation exists.
- `frontend-kitchen`: components display their station's task list (docket + my-station); setup
  lets the user edit a mapping's tasks and role.

## Impact

- **Backend** (`modules/kitchen`): `tasks` JSON column on `product_stations` and
  `order_item_stations` (additive migration `0007`), `PATCH /kitchen/product-stations/{id}`
  (role + tasks), routing copies tasks to tickets, schemas extended.
- **Frontend**: `services/kitchen.api.ts` (`tasks` on `ProductStation`/`Ticket`, update-mapping
  call), `lib/kds/types.ts` + `adapter.ts` (component `tasks`), `KdsItemRow.vue` +
  `KdsMyStation.vue` (render sub-lines), `KitchenSetup.vue` (task list editor), kitchen store.
- No API breaking changes; `tasks` defaults to an empty list everywhere, so existing mappings
  and tickets behave exactly as today until tasks are configured.
