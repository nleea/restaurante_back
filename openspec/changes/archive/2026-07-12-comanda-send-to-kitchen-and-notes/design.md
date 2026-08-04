# Design — send-to-kitchen, kitchen notes, release table

## Context

- `add_item` (orders use case) currently calls `self._kitchen_routing.route_order(...)`
  as a best-effort side effect — every added item immediately gets KDS tickets.
- `route_order` (kitchen) is **idempotent**: it skips items that already have a ticket
  (`if ticket_exists: continue`) and recomputes the order's `kitchen_state`.
- The explicit endpoint **already exists**: `POST /kitchen/orders/{order_id}/route`
  (gated `kitchen.update`).
- `cancel_order` requires the order be open + a reason (≥1 char), records a `Cancellation`
  (audit), sets status `cancelled`, and calls `_free_table` — already frees the table,
  works with zero items.
- KDS tickets are `order_item_stations` rows; `TicketResponse` carries `order_item_id`,
  station, status, `role`, `tasks` — no dish name and no note (the frontend resolves the
  label from `order_item_id`).

## Decision 1 — send-to-kitchen is explicit; items are born pending

Remove the `route_order` call from `add_item`. An added item has no ticket → **pending**.
The comanda's **Enviar a cocina** button calls the existing
`POST /kitchen/orders/{id}/route`; because routing is idempotent, pressing it routes only
the pending items, and pressing it again after adding more (round 2) routes just the new
ones. `kitchen_state` stays `none` until the first send. Inventory still deducts on close;
the recipe safety-net still runs on add. Nothing else about routing changes.

## Decision 2 — per-item `sent` drives the line state

`OrderItemResponse` gains `sent: bool` = "this item has ≥1 kitchen ticket". The orders
repo computes it with one query over `OrderItemStationModel` for the order's items
(cross-module read, consistent with the repo's existing menu/recipes/cash imports). The
comanda shows **EN COCINA** when `sent`, else **PENDIENTE**; **Enviar a cocina** is
enabled when any line is pending.

## Decision 3 — the note is a free-text column on the item, set at add

`order_items.notes text NULL`. `AddItemRequest` gains optional `notes` (bounded, e.g.
≤255). Set once at add; not editable afterward. No price/inventory effect. The note box in
the comanda shows for any product — station gating is intentionally skipped (per the
decision "no importa la estación, solo que el cocinero la lea"); a non-kitchen product
never produces a ticket, so its note is simply never displayed on the KDS.

## Decision 4 — the KDS ticket exposes the note

`TicketResponse` gains `notes: str | None`, sourced by joining `order_items` in the ticket
list query. `KdsItemRow` renders it prominently (`⚠ SIN LECHUGA`) so the cook can't miss
it. The note lives on the item, so all of an item's station tickets carry the same note.

## Decision 5 — "Liberar mesa" is a Salón-panel action

Reuse `cancel_order`. In the table panel (occupied table selected), a **Liberar mesa**
button cancels the order and frees the table, offering one-tap reasons ("Cliente se fue",
"Mesa equivocada") so the required reason needs no typing. Inside the comanda, the
existing **Cancelar comanda** (with reason) stays for orders that already have items.
Because send-to-kitchen is now explicit, releasing an un-sent order has no kitchen impact.

## Risks

- **Tests assume auto-route.** Suites that add an item and expect a KDS ticket must now
  route explicitly. Sweep `add_item`/kitchen/order tests and add explicit `route` calls.
- **Other auto-route callers.** Only `add_item` auto-routed; the KDS route endpoint and
  the "route open orders from the kitchen" screen are unaffected. Verify no delivery flow
  silently depended on add-time routing (dispatch triggers on `ready`, downstream of
  routing, so it's unaffected).
- **`sent` query cost.** One grouped query per items-fetch (not N+1). A menu/order is
  small; acceptable.
- **Note length / injection.** Bound the note server-side; render as text (no HTML) on the
  KDS.
