## Why

With both `orders` (core) and `cash` implemented, the sale loop is still open: a waiter can take a comanda and a cashier can run an arqueo, but there is no way to **charge an order**. `order_payments` (owned by orders) requires a `cash_session_id`, and the cash module deliberately left the payment integration out of scope. This change closes the loop — registering an order payment against the branch's open cash session — so a pilot restaurant can complete the minimum daily flow: **take order → charge → reconcile cash**. It also makes the arqueo reflect real sales, because each payment writes a cash movement into the open session.

## What Changes

- Add a **payment use case** to the orders module: register a payment for an order (amount, method, optional diner reference, charging employee) and list an order's payments.
- A payment is tied to the **branch's currently open cash session**; if no session is open, the charge is rejected (you cannot take money without an open register).
- Registering a payment writes **both** records atomically: an `order_payments` row (the order's money ledger) **and** a `cash_movements` row of type `in`, concept `sale`, with `reference_id = order_id` (so the cash session's arqueo reflects the sale). Cash-method payments thus affect the drawer count; non-cash methods (card/Nequi/Daviplata) are recorded but excluded from the physical-cash reconciliation (per the cash module's rule).
- Enforce business rules: the order MUST exist and be `open`; the charging employee MUST belong to the tenant; `amount` MUST be positive.
- Enforce **multi-tenant + multi-branch isolation** and **RBAC** using the existing `orders.pay` permission for charging and `orders.read` for listing payments.
- No new endpoints prefix — payment endpoints live under the existing `/orders` router.

### Explicitly out of scope (deferred)
- **Auto-close on full payment / partial-payment balance tracking** — payments are recorded but do not change the order status; closing remains a separate action. A future change can add "amount due / fully paid" logic.
- **Refunds / payment voids** — not modeled here.
- **Inventory deduction on close** — separate `orders → inventory` change.

## Capabilities

### New Capabilities
<!-- None — this extends an existing capability. -->

### Modified Capabilities
- `order-management`: adds the ability to charge an order (register payments against the open cash session) and list an order's payments.

## Impact

- **New code**: `orders/application/use_cases/manage_payments.py` (`PaymentService`); extend `orders/domain/ports.py` and `orders/infrastructure/repositories.py` with payment + open-cash-session methods; add payment schemas/endpoints to `orders/infrastructure/api/`.
- **Cross-module reads/writes**: the orders repository reads `cash_sessions` (find the open session) and writes `cash_movements` (the `sale` movement) — both owned by the `cash` module — in addition to its own `order_payments`. No change to cash's own API or requirements.
- **Reused**: `employees` (staff) validation, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`), tenant middleware, RBAC `require_permission`.
- **APIs**: new `POST /orders/{order_id}/payments` and `GET /orders/{order_id}/payments`. No breaking changes.
- **Unblocks**: a restaurant can now complete the charge step; the daily cash arqueo includes sales.
- **Tests**: extend `tests/modules/orders/` with payment flow (open session required, both rows written, arqueo reflects cash sales, RBAC).
