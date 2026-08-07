# Comanda: explicit send-to-kitchen, per-item kitchen notes, and release-table

## Why

Three connected gaps in the order-taking flow surfaced in use:

1. **Items fire to the kitchen the instant they're tapped.** `add_item` auto-routes the
   order to the KDS, so a waiter can't build the full order before the cook starts —
   and a mistaken tap is already cooking. Staff want to compose the comanda, then press
   **Enviar a cocina**.
2. **No way to say "sin lechuga, sin queso".** A diner asks for a plate without an
   ingredient — same price, but the cook must know. There is no note field anywhere on
   an order item, and nothing reaches the KDS.
3. **No clean way to free a table when nobody ordered.** Someone sits, is about to
   order, then leaves. The table is stuck occupied; releasing it isn't obvious.

The good news from exploring: the explicit route endpoint **already exists**
(`POST /kitchen/orders/{id}/route`) and `route_order` is **idempotent** (it only creates
tickets for items without one), so send-to-kitchen works per round for free. And
`cancel_order` **already frees the table** (works even with zero items) — so release is a
UX addition, not backend work.

## What Changes

**Backend (`order-management`, `kitchen-management`)**
- **Stop auto-routing on add.** Remove the `route_order` call from `add_item`; adding an
  item leaves it *pending* (no KDS ticket). The recipe safety-net and inventory-on-close
  behavior are unchanged.
- **Per-item kitchen note.** Add a nullable `notes` text column to `order_items`, set at
  add time via `add_item` (`AddItemRequest.notes`). Not editable afterward (matches "solo
  al agregar"). No price or inventory impact — it's a note.
- **Per-item `sent` indicator.** `OrderItemResponse` exposes `sent` (true when the item
  has ≥1 kitchen ticket), so the comanda can show pendiente vs en cocina per line.
- **Ticket carries the note.** The KDS ticket read (`TicketResponse`) exposes the item's
  `notes` (join to `order_items`) so the cook reads it. Station gating doesn't matter —
  if the item reaches a station, its note travels with it.

**Frontend (`frontend-salon`, `frontend-kitchen`)**
- **Comanda:** each dupe line shows **PENDIENTE** / **EN COCINA** (from `sent`); an
  **Enviar a cocina** button calls the route endpoint and fires the pending lines
  (per-round). A **free-text note box** appears when adding a product (any product; if it
  isn't a kitchen product the note simply never shows on a KDS that has no ticket for it).
  Cancel-with-reason stays inside the comanda.
- **Salón table panel:** a **Liberar mesa** action cancels the order and frees the table,
  with one-tap reasons ("Cliente se fue", "Mesa equivocada") so no typing is forced.
- **KDS:** `KdsItemRow` renders the note prominently (e.g. `⚠ SIN LECHUGA`).

## Impact

- Specs: `order-management` (MODIFIED items + routing), `kitchen-management` (ticket note),
  `frontend-salon` (send + notes + release), `frontend-kitchen` (note on the board).
- Backend: migration `order_items.notes`; orders use case/repo/schema (`add_item` notes,
  drop auto-route, `sent`); kitchen ticket read exposes `notes`; tests updated (auto-route
  assumption → explicit route) + new tests.
- Frontend: `orders.api`/store (`addItem` notes, `sendToKitchen` → route endpoint, `sent`
  on items); comanda dupe + note box + send button; Salón panel "Liberar mesa"; KDS row.

## Out of scope

- Structured modifiers (toggling recipe ingredients off) and any inventory/cost
  adjustment for "sin X" — the note stays free text; the full recipe still deducts.
- Editing the note after the item is added.
- Client-side "batch by round" beyond what the idempotent route endpoint already gives.
- Manager-authorization gating on cancellation (the `requires_authorization` path exists
  but stays off here).
