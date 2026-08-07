# Design — merge Comanda into the Salón

## Context

- **Salón** (`FloorView.vue` + `components/floor/*`) is the real, backend-wired
  front-of-house: a mesas grid + a "Para llevar y domicilios" strip. Taking/opening an
  order currently opens `OrderTicket.vue` in a PrimeVue Dialog. `OrderTicket` bundles
  item-entry (three dropdowns), payments, discount, and close/cancel in one scroll.
- **Comanda** (`ComandaView.vue` + `components/comanda/*` + `lib/comanda.ts`) is the
  in-memory redesign: tap-to-stamp `MenuField`, a perforated `LiveDupe`, a
  `PaymentSheet`. Its model maps ~1:1 onto the real `orders` store
  (`addItem`/`updateQuantity`/`removeItem`/`setDiscount`/`registerPayment`/`closeOrder`/
  `cancelOrder`; getters `itemsOf`/`paymentsOf`/`balanceOf`/`variantIndex`).

## Decision 1 — the order detail is a routed child of the Salón

`/floor/order/:id` renders the Comanda for a real order id. The Salón grid stays at
`/floor`; selecting a table or a no-table order navigates to the child. Deep-linkable,
browser-back returns to the grid, and it matches the repo's master–detail precedent.
`/comanda` (standalone in-memory) redirects to `/floor`.

- Rejected: full-screen overlay (no deep-link/back) and split-screen mesas+comanda
  (too dense on a service tablet).

## Decision 2 — no "Enviar a cocina"; the terminal action is the close-out

Backend `add_item` auto-routes the order to the kitchen — each tap already created the
KDS ticket. So there is no batch send to model. The prototype's tear-off button is
re-pointed:
- Each added line shows a quiet **"en cocina"** state (it's already firing), not a
  pending-to-send state.
- The primary action is **Cobrar → Cerrar / Fiar**. The dupe's big figure stays the
  TOTAL; the tear-off gesture is reserved for closing the order.
- We do NOT introduce client-side "send by round" batching (that invents behavior the
  backend doesn't have).

## Decision 3 — fiado assigns an existing customer at close

`close_order` already: if `remainder > 0` and the order has a `customer_id`, it closes
and records `create_order_credit(customer, remainder)`; if `remainder > 0` and no
customer, it 422s. The only gap is assigning a customer to an already-open order.

**New endpoint:** `POST /orders/{order_id}/customer` `{ customer_id }` (gated
`orders.update`). Validates: order exists in tenant, order is **open**, customer exists
in tenant. Sets `order.customer_id`. Idempotent-ish (re-assign allowed while open).

- Focused endpoint (matches `/close`, `/discount`, `/cancel` style) over a generic
  `PATCH /orders/{id}`.
- Customer picker in cobro is **choose-from-existing only** (search the customers
  directory). No inline create — a "Crear cliente" link routes to `/customers`. New
  customers are born in the Clientes view, keeping that module authoritative.
- No credit-limit gate (backend doesn't enforce one). We only *show* the chosen
  customer's current credit balance as a reference (from the customers store).

**Cobro close state machine:**
```
remainder = total − paid
  remainder ≤ 0 ............... [ Cerrar comanda ]  (paid>total → show vuelto)
  remainder > 0, customer set . [ Fiar y cerrar ]   → close → backend records credit
  remainder > 0, no customer .. blocked → guide: cobrar el resto OR elegir cliente
```

## Decision 4 — the Comanda absorbs OrderTicket entirely

The cobro sheet holds payments (split, per-method), discount edit, close, fiar (assign
+ close), and cancel-with-reason. Channels (dine_in / takeaway / delivery) come from
the order itself; the "Nueva orden" open flow (channel + free table) stays in the Salón
and, on success, navigates to the new detail. `OrderTicket.vue` and `lib/comanda.ts`
are deleted once the detail is live and reaches parity.

## Risks

- **Parity**: `OrderTicket` carries real rules (settlement gate, no-open-cash-session
  409, recipe safety net). The rewired cobro must preserve each — verification walks
  the full close/fiar/cancel/no-session paths.
- **Fresh tenant / no customers**: fiar needs an existing customer; with none, the
  picker is empty and the "Crear cliente" link is the only path — acceptable and
  honest.
- **Deep-link to a closed/stale order**: `/floor/order/:id` must handle an order that's
  already closed or not found (redirect to the grid with a message).
- **Auto-route timing**: because items fire on add, a mistaken tap already hit the KDS;
  removing the line must also reflect on the kitchen — this already works via
  `removeItem`, but the "en cocina" copy shouldn't imply a line is un-sent.
