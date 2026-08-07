# Tasks — require payment (or credit) to close an order

## Backend — order-management (reuses customer_credits)

- [x] `OrdersRepository.payments_total(tenant_id, order_id) -> Decimal` (SUM of order_payments.amount, 0 when none) + port + adapter
- [x] `OrdersRepository.create_order_credit(tenant_id, customer_id, amount, order_id)` — insert `CustomerCreditModel` (total_amount=amount, payment_status="pending", reference_id=order_id) + port + adapter
- [x] `close_order` use case: compute `remainder = order.total - payments_total`; if `remainder > 0` and `order.customer_id is None` → `ValidationError("La comanda no está pagada. Faltan $X. Asigna un cliente para fiar.")` (before any mutation); else consume inventory + close as today; if `remainder > 0` (customer present) → create the order credit for `remainder`
- [x] Confirm the close endpoint maps `ValidationError` to the right HTTP status (422/409 per the codebase) and returns the closed order otherwise
- [x] Tests: close fully paid → ok; close underpaid + no customer → blocked (order stays open, no inventory deduction); close underpaid + customer → ok + a `customer_credit` for the remainder with `reference_id = order_id`; overpay (cash) → ok; fiar 100% (paid 0 + customer) → ok + credit = total
- [x] `ruff check`, `mypy src`, `pytest tests/modules/orders tests/modules/customers` green

## Frontend — frontend-orders-payments

- [x] Service/store: expose `total`, `paid`, `balance` for the ticket; ensure `registerPayment` + `closeOrder` are available; add helpers as needed
- [x] "Cobrar y cerrar" modal: one or more payment lines (method ▼ + amount), live Pagado / Saldo / Vuelto (cash), respecting the design's El Pase styling if reached from the station, else the orders UI's own style
- [x] "Fiar el resto" toggle — enabled ONLY when the order has a registered customer; shows the amount going to credit
- [x] Confirm flow: register each split payment, then close; disable "Cobrar y cerrar" while `balance > 0` unless "Fiar" is on (and a customer exists); surface `409` (no open cash session) and the backend "faltan/ asigna cliente" error inline
- [x] Block the plain "Cerrar" path when underpaid + no customer (or route it through the modal)
- [x] `pnpm type-check`, `pnpm lint`, `pnpm build` green

## Verification

- [x] Live: order with registered customer → pay 50% split (cash + Nequi), fiar the rest → closes, shows in caja summary, and a credit appears for the customer
- [x] Live: order without customer, underpaid → close is blocked with the clear message
- [x] Live: fully paid (incl. overpay/change) → closes and appears in the cash station KPIs
