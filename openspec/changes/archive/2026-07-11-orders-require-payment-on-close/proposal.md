# Require payment (or customer credit) to close an order

## Why

An order can currently be closed with **no payment registered** — `close_order`
never checks payments. A closed, unpaid order is invisible to cash and finance
(the shift summary and Z report aggregate only orders that have a payment linked
to the session), so a real sale silently vanishes from the caja and the drawer
never reconciles. This was hit in practice: a comanda was closed without
"registrar pago" and never appeared in the cash station.

The fix is a business rule: **you cannot close a comanda that isn't settled.**
Settlement may be split across several payment methods, and — only for a
**registered customer** — the unpaid remainder may be left on **credit (fiado)**.

## What Changes

Rule at close:

```
paid = Σ payments(order)   ·   total = order.total   ·   remainder = total − paid
remainder <= 0                       → close (fully paid; cash overpay = change)
remainder > 0 AND order.customer_id  → close AND record a customer credit for the remainder
remainder > 0 AND no customer        → BLOCK: "Faltan $X — asigna un cliente para fiar"
```

Confirmed decisions: full settlement required to close; may be split across
methods; a registered customer may be fiado up to 100% (payment 0 allowed); no
credit limit is enforced (the data model has none today).

The **customer credit (fiado) machinery already exists** — `customer_credits`,
`customer_credit_payments`, and `CustomersService.register_credit` /
`register_credit_payment` (a cash settlement already enters the drawer). This
change only **wires it into order close**: it does not build receivables.

**Backend (`order-management`, reusing `customer-management`)**
- `close_order` computes the paid total and blocks close when `remainder > 0`
  and the order has no `customer_id`.
- When `remainder > 0` and a `customer_id` is present, close proceeds and a
  `customer_credit` is created for the remainder (`reference_id = order_id`,
  `payment_status = pending`), following the existing cross-module orders→other
  repo pattern (as `consume_inventory_for_order` already does).

**Frontend (`frontend-orders-payments`)**
- A "Cobrar y cerrar" flow: register one or more payments (multiple methods),
  with a live balance and cash change, then close.
- A "Fiar el resto" option, enabled **only** when the order has a registered
  customer, showing the amount that will go on credit.
- The close action is blocked (with a clear message) when the order is underpaid
  and has no customer; the derived balance already tracked by the payments state
  drives this.

## Impact

- Specs: `order-management`, `frontend-orders-payments` (reuses `customer-management`).
- Backend: `orders` close use case + repo (`payments_total`, create-order-credit);
  no new tables (reuses `customer_credits`). New tests. No migration.
- Frontend: the order ticket's payment/close UI in `components/orders/*` +
  `stores`/`services` as needed.

## Out of scope

- Credit limits per customer; credit aging/reminders.
- Editing/voiding a credit created at close (settle via the existing
  `register_credit_payment` flow).
- The automatic `sale` cash-movement in the station feed (still deferred to the
  broader orders→cash tape work).
