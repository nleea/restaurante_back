## Context

The Comandas screen (`frontend-orders`) is implemented as a master–detail: `OrdersView` →
`OrdersPanel` (list) → `OrderTicket` (detail with items, discount, close, cancel). The orders
store (`stores/orders.ts`) follows a strict **write-through** discipline: every mutation calls
the API then refetches the affected order so the client never computes order totals locally — it
only computes the per-item `unit_price` it submits.

The backend payment contract already exists and is settled, so this change is client-only:

- `POST /orders/{order_id}/payments` — perm `orders.pay`. Body
  `{ amount: Decimal>0, method: str(1..30), employee_id: UUID, diner_reference?: str(≤50) }`.
  The use case (`manage_payments.py`) requires the order to be **open**, the employee to exist,
  and resolves the branch's **open cash session** server-side; if none is open it raises
  `ConflictError` → `409`. The response carries the resolved `cash_session_id`.
- `GET /orders/{order_id}/payments` — perm `orders.read` — returns the order's payments.
- The order header already exposes the authoritative `total` (string Decimal).

`method` is a free-form string on the backend (no enum), so the **client owns** the list of
offered methods. The current employee is already resolved in the store via
`getMyEmployee()` (`GET /staff/employees/me`), the same primitive used for every order op.

## Goals / Non-Goals

**Goals:**
- Close the orders → cash loop from the UI: register one or more payments against an open order
  and see total / paid / balance update.
- Reuse the existing write-through pattern, `apiError` helpers, PrimeVue inputs, and COP
  formatting already in `OrderTicket`.
- Fail clearly and recoverably when there is no open cash session.

**Non-Goals:**
- Opening/closing cash sessions (owned by the `cash-management` screen).
- Refunding or voiding a registered payment (no backend endpoint today).
- Split-by-seat tendering, tipping, change calculation, or receipt printing.
- Enforcing full payment before close in the client beyond a warning (backend keeps pay and
  close as independent steps).

## Decisions

**1. New `frontend-orders-payments` capability, extend existing files in place.**
Payments are a distinct, additive behavior, so they get their own capability spec, but the code
lives in the existing `orders.api.ts` / `orders.ts` / `OrderTicket.vue` rather than new modules —
keeping the master–detail screen cohesive. Alternative (a separate Payments view) was rejected:
tendering belongs next to the ticket it settles.

**2. Compute paid/balance on the client from the payments list; never store balance.**
The order's `total` is authoritative from the server; `paid = Σ payment.amount` and
`balance = max(0, total − paid)` are derived getters. This mirrors the store's existing rule of
trusting server totals and only deriving presentational values. We do **not** invent an order
`amount_paid` field the backend doesn't return. Money math uses `Number(...)` on the Decimal
strings for display parity with the existing item-price handling; amounts submitted are formatted
with `.toFixed(2)` like `unit_price`.

**3. The 409 is the source of truth for "no open cash session"; no proactive `cash.read` probe.**
`GET /cash/branches/{id}/open-session` requires `cash.read`, which a cashier holding only
`orders.pay`/`orders.read` may lack (the same RBAC asymmetry that `GET /staff/employees/me`
solved for `employee_id`). Probing it would either 403 for cashiers or leak a cash permission
requirement into this screen. Instead we attempt the payment and map `isConflict(e)` (409) to an
actionable message. Simpler, correct for every role, and avoids a second permission dependency.

**4. Client owns the payment-method list.** Offer Efectivo, Nequi, Daviplata, Tarjeta,
Transferencia (Colombia-oriented per the product brief) as a small typed constant submitted as
the `method` string. Centralizing it in the service/store keeps labels and submitted values in
one place; the backend accepts any ≤30-char string so no contract coupling.

**5. Permission gating mirrors the ticket's existing pattern.** Use `auth.can('orders.pay')` for
the registration controls exactly as `OrderTicket` already does for `orders.update` /
`orders.cancel`; the summary and list remain visible to anyone with `orders.read`.

**6. Store shape: `paymentsByOrder: Record<string, OrderPayment[]>`** parallel to
`itemsByOrder`, loaded by `fetchPayments(orderId)` and refreshed inside `registerPayment` —
consistent with `fetchItems` / `refreshOrder`.

## Risks / Trade-offs

- **Overpayment is not prevented client-side** → the amount input prefills the balance and the
  panel warns when entered > balance, but submission is allowed (backend accepts it). Acceptable:
  cash tendering legitimately exceeds the balance; refunds/change are out of scope.
- **Stale balance if payments were added elsewhere** → write-through refetch on register and
  `fetchPayments` on ticket open keep it fresh for the single-cashier pilot flow; no realtime
  sync is attempted (consistent with the rest of the screen).
- **`employee_id` requires a linked employee** → reuse the store's existing
  `currentEmployee` guard (throws "Tu usuario no está vinculado a un empleado."), so a non-employee
  account cannot register a payment, matching `openOrder`/`cancelOrder`.
- **Float math on Decimal strings** → only used for display/derived balance, never sent back;
  submitted amounts are `.toFixed(2)` strings, identical to the proven `unit_price` path.

## Migration Plan

Pure additive frontend change; no data migration, no backend deploy. Ship behind the existing
`orders.pay` permission (already seeded). Rollback is reverting the three files and their tests —
no persisted client state to clean up.

## Open Questions

- Final wording/order of the method list and whether a tenant-configurable method set is wanted
  later (out of scope now; constant is centralized to make that easy).
