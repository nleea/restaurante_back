# Design — require payment (or credit) to close an order

## The rule, precisely

```
paid      = Σ order_payments.amount for the order (any method)
total     = order.total
remainder = total − paid

remainder <= 0                        → close. (Cash overpayment is change/vuelto —
                                         payments may sum to more than total.)
remainder > 0 and customer_id != null → close, then create customer_credit(
                                         customer_id, total_amount = remainder,
                                         reference_id = order_id, status = pending).
remainder > 0 and customer_id == null → ValidationError, order stays open:
                                         "La comanda no está pagada. Faltan $X.
                                          Asigna un cliente para fiar."
```

`remainder` may equal `total` (100% credit / paid = 0) for a registered customer.
No credit limit is checked (the model has none).

## Where the logic lives (cross-module)

The codebase already reaches across modules from the **orders repository** —
`close_order` calls `consume_inventory_for_order`, which mutates inventory tables.
We follow that established pattern rather than introduce an application-level
dependency from `OrdersService` to `CustomersService`:

- `OrdersRepository.payments_total(tenant_id, order_id) -> Decimal` — `SUM(amount)`
  over `order_payments` for the order (0 when none).
- `OrdersRepository.create_order_credit(tenant_id, customer_id, amount, order_id)` —
  inserts a `CustomerCreditModel` (`total_amount = amount`, `payment_status =
  "pending"`, `reference_id = order_id`). Mirrors what `CustomersService.
  register_credit` writes; the order's `customer_id` is already a valid FK, so the
  `require_customer` guard is redundant here.

`close_order` use case orchestration:

```
order = require_open_order(...)
paid  = repo.payments_total(...)
remainder = order.total - paid
if remainder > 0 and order.customer_id is None:
    raise ValidationError("… Faltan $remainder. Asigna un cliente para fiar.")
consume_inventory_for_order(...)          # unchanged
updated = repo.close_order(...)           # unchanged: status/closed_at/customer stats/free table
if remainder > 0:                         # customer_id guaranteed present here
    repo.create_order_credit(..., amount=remainder, order_id=order.id)
return updated
```

Ordering note: validate BEFORE mutating (no inventory deduction / close on a
rejected order). Credit is created after the successful close so `reference_id`
points at a genuinely closed order.

## Why not require the payment inside close

Payments are registered through the existing `POST /orders/{id}/payments`, which
resolves the branch's open cash session and links the payment to it (this is what
feeds the caja summary). The new "Cobrar y cerrar" UI simply registers each split
payment via that endpoint, then calls close. Close stays a pure guard + credit
step; it does not itself take money. Fully-on-credit closes register no payment
and never touch the drawer.

## Frontend flow

The order ticket already tracks a derived balance (`frontend-orders-payments`).
The change turns the informational balance into a gate:

```
[ Cobrar y cerrar ]  opens a modal:
   line items: (method ▼, amount)  + "añadir método"
   Pagado: $P    Total: $T    Saldo: $ (T−P)   Vuelto: $ (P−T if cash & >0)
   [x] Fiar el resto → $ (T−P)      (only enabled if order has a registered customer)
   [ Cobrar y cerrar ]  disabled while Saldo>0 and "Fiar" off (or no customer)
On confirm: for each line → registerPayment(order, {method, amount});
            then closeOrder(order).  Errors surface inline (409 = no open caja).
```

## Risks / assumptions

- **[assumption] Overpayment = change.** `Σ payments` may exceed total (cash
  change); `remainder <= 0` closes. The drawer's expected-cash already reconciles
  cash-in vs out, so change handling is a UI concern, not a data one.
- **[assumption] One credit per underpaid close**, amount = remainder. Re-closing
  is impossible (order already closed), so no double credit.
- **[verify] Permissions.** Close keeps its existing `orders.update`/close gate;
  creating the credit is part of close (no separate customer permission required).
  Confirm this matches product intent.
- **[assumption] No credit limit / no branch on credit** (model is tenant-scoped,
  matches the existing `register_credit`).
