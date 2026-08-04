## Context

`orders` (core) and `cash` are both implemented and archived. Orders left payments out of scope (blocked on cash); cash left the order integration out of scope. This change is the seam between them. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English-only identifiers, "small complete system".

Facts confirmed in code:
- `order_payments` (owned by orders, branch-scoped): `order_id`, `cash_session_id` (NOT null, FK → `cash_sessions`), `amount`, `method`, `diner_reference`, `employee_id`. The `OrderPayment` domain entity already exists.
- `cash_movements` (owned by cash, branch-scoped): `cash_session_id`, `type`, `concept`, `amount`, `method`, loose `reference_id`. `cash_sessions` carries `status` (`open`/`closed`).
- Cash reconciliation (`expected_amount`) sums only `method = 'cash'` movements; non-cash methods are recorded but excluded.
- The orders repository already imports models from other modules (menu); importing cash models is the same established pattern.
- Permission `orders.pay` already exists; `orders.read` already used by the orders router.

## Goals / Non-Goals

**Goals:**
- A `PaymentService` in the orders module to register an order payment and list payments.
- A payment ties to the branch's open cash session and atomically writes `order_payments` + a `cash_movements` (`in`/`sale`).
- Make the arqueo reflect cash sales automatically.
- Tenant isolation, reference validation, RBAC (`orders.pay` / `orders.read`).
- Extend the orders test suite.

**Non-Goals:**
- Auto-close on full payment, partial-payment balance/"amount due" tracking.
- Refunds / voids / payment reversal.
- Inventory deduction on close (separate `orders → inventory` change).
- Any change to the cash module's public API or requirements.

## Decisions

**1. The integration lives in the orders module (the higher-level consumer).**
A new `orders/application/use_cases/manage_payments.py` (`PaymentService`) composes the orders repository. The orders repository — which already reaches into other modules' models — gains methods to read the open cash session and to write the payment + movement. Rationale: orders depends on cash, not vice-versa; co-locating the seam in orders avoids a new cross-module service layer and matches how the orders repo already imports menu models.

**2. Payment + cash movement are written atomically in one repository method.**
`OrdersRepository.register_payment(payment)` inserts the `OrderPaymentModel` AND a derived `CashMovementModel` (`type='in'`, `concept='sale'`, `method=payment.method`, `amount=payment.amount`, `reference_id=order_id`, same `cash_session_id`/`branch_id`/`tenant_id`) and commits **once**. Rationale: a payment that recorded the order side but not the cash side (or vice-versa) would corrupt the arqueo; a single transaction is the correct consistency boundary. This is stronger than the per-write-commit idiom used elsewhere, and justified because the two rows are one logical fact.

**3. The open session is resolved server-side from the order's branch, not supplied by the client.**
`register_payment` looks up the branch's `open` cash session; missing → `ConflictError` ("no open cash session"). Rationale: the client should not choose which session receives the money; it is always the branch's current open register. Prevents posting to a closed/foreign session.

**4. Charge only `open` orders.**
Guard: order must exist and be `open` (not `closed`/`cancelled`) → else `ConflictError`. Rationale: consistent with the orders state machine; closing remains a separate step. Partial payments are allowed (multiple payments per order) but do not change status.

**5. Validation split.**
Pydantic: `amount > 0`, `method` required, `employee_id` required. Service: order exists + open, employee in tenant, open session exists. Errors reuse `shared/domain/errors`.

## Risks / Trade-offs

- **Concurrent payments + session close**: a payment could post to a session being closed in parallel. → Acceptable at pilot scale (one cashier/branch); the session lookup + writes share one session/transaction. A later hardening can lock the session row.
- **No balance enforcement**: payments can exceed the order total (over-collection) since we don't track amount-due. → Accepted as out of scope; surfaced as an open question. The order's `total` and the sum of payments are both queryable for a future "amount due" feature.
- **Cross-module write from orders into `cash_movements`**: couples orders to cash's table shape. → Accepted; it is the explicit integration point, and orders already imports other modules' models. Cash's API/requirements are untouched.
- **sqlite vs Postgres**: `Numeric` arithmetic and FK constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — `order_payments` and `cash_movements` exist in migration `0002`. Autogenerate should be a no-op (verify statically if Postgres unavailable).
2. Deploy is additive — two new endpoints under `/orders`. Reverting the code removes them.

## Open Questions

- Should a payment that brings total paid ≥ order total auto-close the order? (Default: no; keep close explicit.)
- Should over-collection (payments exceeding `total`) be rejected or allowed (tip/rounding)? (Default: allow; revisit with amount-due tracking.)
- Should the payment response include the order's remaining balance? (Default: out of scope now.)
