## Why

The Comandas screen (`frontend-orders`) lets staff open orders, manage items, apply a discount
and close, but there is **no way to register a payment** — so the operational sales loop
(orders → cash) is never closed from the UI. The backend already exposes the full payment
contract (`POST/GET /orders/{id}/payments`, settled against the branch's open cash session);
only the client layer is missing. This is the last piece needed for a pilot restaurant to take
money for a table without dropping back to paper.

## What Changes

- Add a **payments service layer**: `registerPayment` and `listPayments` over
  `/orders/{id}/payments`, plus typed `OrderPayment` / `RegisterPaymentInput`.
- Extend the **orders store** to load an order's payments, register a payment (write-through:
  refetch payments + order header afterward), and expose derived `paidOf(orderId)` and
  `balanceOf(orderId)` getters computed as `total − Σ payments`.
- Add a **payment panel** inside `OrderTicket`: shows total / paid / balance, a method
  selector (Efectivo, Nequi, Daviplata, Tarjeta, Transferencia), an amount input prefilled
  with the outstanding balance, an optional diner reference, and the list of payments already
  registered. The action is gated by the `orders.pay` permission.
- **Guide the cashier to close on settlement**: once the balance reaches zero the panel
  surfaces the existing "Cerrar comanda" affordance; while a balance remains, closing is
  discouraged with a warning (the backend keeps close and pay as separate steps).
- **Surface the "no open cash session" case**: the payment POST returns `409` when the branch
  has no open cash session — map it to a clear, actionable message instead of a generic error.

Non-goals: opening/closing cash sessions (that is the `cash-management` screen), refunds/voids
of a registered payment, split-by-seat tendering, and printing receipts.

## Capabilities

### New Capabilities
- `frontend-orders-payments`: registering and reviewing payments for an open order from the
  Comandas screen — payment methods, amount/balance handling, the open-cash-session
  precondition, and permission gating by `orders.pay`.

### Modified Capabilities
<!-- None. The existing frontend-orders capability is extended additively by the new
     capability above; no current frontend-orders requirement changes its behavior. -->

## Impact

- **Frontend code**: `front/src/services/orders.api.ts` (new payment calls + types),
  `front/src/stores/orders.ts` (payments state, getters, action), and
  `front/src/components/orders/OrderTicket.vue` (payment panel). New unit tests under
  `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Backend**: none — consumes existing `POST /orders/{id}/payments` (`orders.pay`),
  `GET /orders/{id}/payments` (`orders.read`), and the order's server-computed `total`.
- **Permissions/RBAC**: relies on `orders.pay`; no new permission codes. The branch open-cash
  session is resolved server-side, so the client needs no `cash.read`.
- **Dependencies**: no new packages; reuses PrimeVue inputs, the Axios instance, and the
  `apiError` helpers (`statusOf` / `isConflict`).
