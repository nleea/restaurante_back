# Tasks — send-to-kitchen, kitchen notes, release table

## Backend — order items: note + stop auto-route + sent

- [x] 1.1 Migration `0012_order_item_notes` (chains from head `2ed5e401d539`); applied to Postgres.
- [x] 1.2 `OrderItemModel` + `OrderItem` entity: `notes` (+ derived `sent`).
- [x] 1.3 `add_item`: accepts `notes` (trimmed→null); **auto-route block removed**; recipe
  safety-net kept.
- [x] 1.4 `AddItemRequest.notes` (≤255); router passes it; `create_item` persists it.
- [x] 1.5 `OrderItemResponse`: `notes` + `sent`; repo computes `sent` via one grouped
  `OrderItemStationModel` query (cross-module import).

## Backend — KDS ticket carries the note

- [x] 2.1 `TicketResponse.notes`; `list_tickets` joins `order_items` for the note.

## Backend — tests

- [x] 2.2 Rewrote the two auto-route tests to route explicitly (`test_item_add_does_not_route_until_send`, after-ready rollup).
- [x] 2.3 New tests: item note persisted+returned; `sent` false→true after route; KDS
  board exposes the note; adding an item creates no ticket. Full suite 263 green, ruff+mypy clean.

## Frontend — data layer

- [x] 3.1 `orders.api`/`orders` store: `addItem(orderId, variantId, qty, notes?)` passes
  `notes`; `OrderItem` type gains `notes` + `sent`; add `sendToKitchen(orderId)` →
  `POST /kitchen/orders/{id}/route` (via kitchen api) then `refreshOrder`.

## Frontend — comanda

- [x] 4.1 Note box: when adding a product, a free-text note field ("sin lechuga…") →
  passed to `addItem`. Shown on the dupe line.
- [x] 4.2 Per-line state: **PENDIENTE** (`!sent`) / **EN COCINA** (`sent`).
- [x] 4.3 **Enviar a cocina** button: enabled when any line is pending; calls
  `sendToKitchen`; lines flip to EN COCINA. Supports rounds (add more → send again).
- [x] 4.4 Keep **Cancelar comanda** (with reason) in the cobro/detail.

## Frontend — Salón + KDS

- [x] 5.1 Table panel: **Liberar mesa** for the selected occupied table → `cancelOrder`
  with one-tap reasons ("Cliente se fue", "Mesa equivocada"); the table returns to libre.
- [x] 5.2 `KdsItemRow`: render the item's `notes` prominently (e.g. `⚠ SIN LECHUGA`).

## Verification

- [x] 6.1 Backend `pytest` green (updated + new tests); ruff + mypy.
- [x] 6.2 Frontend `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build` green.
- [ ] 6.3 Live walk: add items (pending, note "sin lechuga") → nothing in KDS yet → Enviar
  a cocina → tickets appear with the note → add another → Enviar again routes only it →
  Liberar mesa on an empty table frees it → cancel-with-reason on a sent order.
