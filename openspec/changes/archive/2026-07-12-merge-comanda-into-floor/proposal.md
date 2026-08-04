# Merge the Comanda redesign into the Salón as the real order screen

## Why

The order-taking screen was redesigned as **Comanda** (`/comanda`, in-memory prototype):
a tap-to-stamp menu field + a live perforated "dupe" + a payment sheet. It's a much
better view than today's `OrderTicket.vue` — the raw-PrimeVue panel (three-dropdown
add-item + payments + close, all in one scroll) that opens as a Dialog from the Salón.

We want **one** order surface: the Comanda interaction, wired to the real backend,
*inside* the Salón flow — reached by opening a table (or a takeaway/delivery order).
`/comanda` (in-memory) becomes the template and retires; `OrderTicket.vue` retires too.

Exploring surfaced two things that shape the design:

1. **Items auto-route to the kitchen on add** (backend `add_item`). There is no
   "fire/send" step — every tap already reached the KDS. So the prototype's hero
   button "Enviar a cocina" doesn't map to anything real. The terminal action becomes
   the real close-out (**Cobrar → Cerrar / Fiar**); "en cocina" is a per-line state.
2. **Fiado (credit) needs a customer on the order, and there's no way to assign one
   after opening.** `close_order` already records the unpaid remainder as a customer
   credit *when the order has a `customer_id`* — but the Salón opens tables without a
   customer and no endpoint sets one later. So today a dine-in table effectively
   cannot be fiado. Fixing this is the one backend change here.

## What Changes

**Backend (`order-management`)** — one focused addition
- `POST /orders/{order_id}/customer` `{ customer_id }` assigns a customer to an
  **open** order (gated `orders.update`; validates the customer exists in the tenant;
  rejects on a closed/cancelled order). Everything else (the fiado close, the credit
  record) already exists and is reused unchanged.

**Frontend (`frontend-salon`, `frontend-orders-payments`)** — the merge
- New routed child **`/floor/order/:id`** renders the Comanda for a real order
  (deep-linkable, browser back returns to the Salón). The Salón stays the home
  (mesas grid + "Para llevar y domicilios"); opening/taking an order navigates here
  instead of opening the `OrderTicket` Dialog.
- The Comanda components (`MenuField`, `ProductTile`, `VariantPopover`, `LiveDupe`,
  `DupeLine`, `PaymentSheet`) are rewired from `lib/comanda.ts` to the **real
  `orders` + `menu` + `customers` stores**. Only orderable products are shown (active
  branch price + an active variant). Each line, once added, shows an "en cocina"
  state — no batch "Enviar a cocina" button.
- The **cobro sheet absorbs everything** `OrderTicket` did: register split payments
  (efectivo/tarjeta/nequi/transferencia), edit the discount, show vuelto, and close.
  Fiado: when a balance remains, pick an **existing** customer (search the customers
  directory — no inline create; a "Crear cliente" link routes to the Clientes view),
  assign them to the order, then **Fiar y cerrar** (backend records the credit).
  Cancel-with-reason lives here too.
- Retire `OrderTicket.vue`, `lib/comanda.ts`, and the standalone `views/ComandaView.vue`
  route (`/comanda` redirects to `/floor`) once the routed detail is live.

## Impact

- Specs: `order-management` (ADDED assign-customer), `frontend-salon` (MODIFIED —
  routed order detail), `frontend-orders-payments` (MODIFIED — cobro + fiado-by-assign).
- Backend: orders use case + repo + schema + router + tests (one endpoint).
- Frontend: `orders.api`/`orders` store gain `assignCustomer`; new router child; the
  Comanda components move to real stores; `FloorView` navigates to the detail;
  `OrderTicket.vue` + `lib/comanda.ts` + standalone Comanda route removed.
- The settlement/fiado business rules (`order-close-requires-payment`) are preserved,
  now actually reachable for dine-in.

## Out of scope

- Creating a customer inline from cobro (deferred — use the Clientes view).
- Any credit **limit** enforcement at close (backend doesn't gate on a cap today; we
  only *show* the customer's current credit balance as a reference when picking).
- Changing the auto-route-to-kitchen behavior (no client-side "send by round" batching).
- Unit conversion, variant-option composition, or other untouched domain rules.
