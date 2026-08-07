# Design: kitchen-station-task-lists

## Context

Since `kds-components-recipes-realtime`, a dish renders as one component per routed station,
named by the mapping's `role` (fallback: station label). That name is a single ≤60-char string
per (product, station) — too coarse when one station owes several distinguishable things to the
same dish. The user decided (explore session, 2026-07-01): tasks must be **readable and
itemized**, but **not** individually checkable — one status/timer per station stays correct.
Deriving tasks from the recipe/BOM was considered and rejected: different grain (ingredient ≠
task), different axis (BOM is per variant, routing per product), and it would couple the
inventory-costing hinge to kitchen workflow.

Current relevant shapes:

- `ProductStationModel` (`product_stations`): unique `(product_id, kitchen_station_id)`, `role`
  nullable ≤60. Only attach/detach endpoints exist — no update.
- `OrderItemStationModel` (`order_item_stations`): `role` denormalized at routing, frozen;
  unique `(order_item_id, kitchen_station_id)` (migration `0006`).
- Routing loop (`manage_kitchen.py`) copies `role` from `list_stations_for_product`.
- Frontend adapter groups tickets per order item; `KdsComponent.name = role ?? station label`.
- `recipe_details` (migration `0005`) already set the precedent of JSON string-array columns.

## Goals / Non-Goals

**Goals:**

- Per (product, station), an ordered list of task names the cook can read on the component —
  in the docket rows and in my-station — e.g. Parrilla: "Carne de hamburguesa", "Tocineta
  ahumada".
- Tasks are config: editable in Configuración (with role), frozen onto tickets at fire time.
- Zero behavior change where no tasks are configured (empty list ≡ today).

**Non-Goals:**

- No per-task status/check-off, tickets, timers or alerts (a future promotion path: the same
  `tasks` data could become one ticket per task without re-configuring).
- No recipe/BOM coupling; no recipe-based task suggestions in this change (noted as a possible
  later convenience).
- No printing, no reordering UI beyond list order as entered.

## Decisions

### D1 — Tasks as a JSON string array on the mapping, denormalized onto the ticket

`product_stations.tasks` and `order_item_stations.tasks`: JSON arrays of strings (each ≤60
chars, ≤10 per mapping, validated in the schema layer; empty list default). Routing copies the
mapping's tasks onto each created ticket next to `role` — same freeze-at-fire semantics, so the
board never shows tasks the kitchen wasn't fired with. *Alternatives rejected:* a `tasks` table
(overkill for an ordered text list — same reasoning as `recipe_details.steps`); resolving tasks
client-side from mappings (extra fetch per product, and breaks the frozen-at-fire guarantee).

### D2 — One mapping update endpoint instead of widening attach

`PATCH /kitchen/product-stations/{mapping_id}` accepting partial `{role?, tasks?}` — mirrors
`PATCH /kitchen/stations/{id}` (`exclude_unset` semantics). Attach keeps accepting `role` and
gains optional `tasks` for one-shot setup. This also fixes today's annoyance that changing a
role requires detach/re-attach. `kitchen.update` gated, tenant-guarded like the rest.

### D3 — Frontend: tasks ride the existing component, purely presentational

`KdsComponent` gains `tasks: string[]` (adapter copies `ticket.tasks ?? []`). Rendering:

- **Docket** (`KdsItemRow`): under each component row, its tasks as small mono sub-lines
  (`· Carne de hamburguesa`), dimmed when the component is done. No new interactions.
- **My-station** (`KdsMyStation`): the row shows the component name and its task list, so the
  cook at the grill reads exactly what the dish needs from them.
- Status, cold-timers, alerts, tap-to-advance: untouched (component-level).

### D4 — Setup UX: task chips per mapping row

`KitchenSetup.vue`'s product↔station mapping rows gain an inline editor: the mapping shows its
role and task chips; editing opens name + add/remove/reorder-by-position of task strings, saved
via the new PATCH (write-through refetch of the product's mappings, per store discipline).

## Risks / Trade-offs

- [Tickets frozen before tasks were configured show no tasks] → expected and consistent with
  `role` semantics; the next fired order carries them. Document in Configuración copy.
- [JSON column skips per-element DB validation] → validated in Pydantic (length, count) and the
  frontend trims/dedupes; same trade-off already accepted for `recipe_details.steps`.
- [Docket rows get taller with many tasks] → cap at 10 tasks per mapping; sub-lines use the
  compact mono style; ready components collapse their task list (done is done).
- [Two sources of dish detail (tasks vs recipe steps) could drift] → they answer different
  questions (what vs how); the drawer remains one tap away for the how.

## Migration Plan

1. Migration `0007_station_task_lists`: add `tasks` JSON NOT NULL DEFAULT '[]' to
   `product_stations` and `order_item_stations`. Additive; instant on current data volumes.
2. Deploy backend (old frontend ignores the new field), then frontend.
3. Configure task lists for the pilot products in Configuración.
4. Rollback: revert code; the columns are inert if unused.

## Open Questions

- None blocking. (Recipe-based task-name suggestions in the setup form noted as a future
  convenience, out of scope here.)
