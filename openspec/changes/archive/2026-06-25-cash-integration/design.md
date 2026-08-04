## Context

The orders module already wires payments into the cash drawer; this change mirrors that exact
pattern for purchasing supplier payments and customer fiado settlements. The established precedent
(verified):

- **Open-session lookup** (orders repo): `select(CashSessionModel).where(tenant_id, branch_id,
  status == "open")` → first; the use case raises `ConflictError("No hay sesión de caja abierta…")`
  when it returns `None`.
- **Cash movement write** (orders repo, atomic with the payment): a `CashMovementModel(tenant_id,
  branch_id, cash_session_id, type, concept, amount, method, reference_id)` added to the same
  session and committed together.
- Orders uses **direct cross-module imports** of `CashSessionModel` / `CashMovementModel` from
  `restaurante.modules.cash.infrastructure.models`, and `concept = "sale"`, `type = "in"`,
  `reference_id = order_id`.
- `CashMovementModel`: `{ tenant_id, branch_id, cash_session_id, type(str20), concept(str50),
  amount(Numeric 12,2), method(str30), reference_id(uuid|null) }`. `CashSessionModel.status` is
  `"open"`/`"closed"`.

Both new payment paths already load what's needed: purchasing's `register_payment` use case loads
the `PurchaseOrder` (which has `branch_id`); customers' `register_credit_payment` validates the
employee and can read `EmployeeModel.branch_id`. Customer credits carry **no** `branch_id`, so the
drawer must be resolved from the paying employee.

## Goals / Non-Goals

**Goals:**
- Make the caja reflect real cash flow: supplier cash payments leave the drawer, fiado cash
  settlements enter it — so the arqueo reconciles.
- Reuse the orders→cash mechanism verbatim (same models, same open-session rule, same atomic write,
  same `ConflictError`), so behavior is consistent and the blast radius is small.

**Non-Goals:**
- Finance expense → cash (a deliberate independent-ledger decision); auto-fiado on unpaid orders;
  void/reversal of a payment and its cash movement; backfilling historical payments; new cash
  endpoints (the write is an internal cross-module post).

## Decisions

**1. Cash-method payments require an open session; non-cash are untouched.** A `method == "cash"`
purchase/fiado payment posts a cash movement and therefore **requires** an open session on the
target branch, raising `ConflictError` if there is none — identical to how an order cash payment
behaves. Card/transfer/Nequi payments write no cash movement and impose no session requirement. This
keeps "if it's cash, it must hit an open drawer" consistent across all three payment types.

**2. Movement direction by economic meaning.** A supplier payment is cash **leaving** the
drawer → `type = "out"`, `concept = "purchase_payment"`, `reference_id = purchase_order_id`. A fiado
settlement is the customer **paying us** → `type = "in"`, `concept = "credit_payment"`,
`reference_id = customer_credit_id`. (Orders' sale is `in`/`sale`.) The cash store's running
expected-cash already counts only `method == "cash"` movements, so these adjust the drawer correctly.

**3. Branch resolution: order for purchasing, paying employee for fiado.** Purchasing posts to the
purchase order's `branch_id` (the order is already loaded). Fiado credits have no branch, so the
settlement posts to the **paying employee's** branch (`EmployeeModel.branch_id`) — the employee is
who physically takes the cash, so their drawer is the right one. This is an inference (documented as
an open question) but the only sensible mapping given the tenant-level credit model.

**4. Write the movement in the paying module's repository, atomically.** Mirroring orders, the
purchasing and customers repositories import the cash models and add the `CashMovementModel`
alongside the payment model in one `commit()`. The **use case** does the open-session lookup (and
raises on absence) and passes the resolved `branch_id` + `cash_session_id` into the repo's
`create_payment` / `create_credit_payment`; for non-cash it passes nothing and no movement is
written. A small internal value (e.g. a `CashPosting(branch_id, cash_session_id)` dataclass or two
optional kwargs) carries the resolved target into the repo.

**5. Frontend is polish only.** The integration is server-side; the existing payment dialogs already
exist. Two small UX touches: (a) map the new 409 to a clear "no hay una caja abierta para registrar
el pago en efectivo" message in the procurement and customers payment dialogs; (b) label the cash
ledger concepts (`sale`→"Venta", `purchase_payment`→"Pago a proveedor", `credit_payment`→"Abono
fiado") instead of raw codes in `ActiveDrawer` (and the history detail). A tiny shared label map.

## Risks / Trade-offs

- **Behavior change**: a cash purchase/fiado payment now fails without an open session. → Intended
  and consistent with orders; surfaced clearly in the UI. Operators already keep a session open to
  take order payments.
- **Fiado branch via employee** could be wrong if an employee settles a credit for a different
  branch's drawer. → At pilot scale (one branch) this is moot; documented as an open question for the
  multi-branch phase. The alternative (no branch at all) leaves cash unreconciled, which is worse.
- **No backfill**: payments made before this ships have no cash movement. → Acceptable; the arqueo
  is forward-looking. Noted, not silently skipped.
- **Atomicity**: the payment and its cash movement commit together, so a movement never exists
  without its payment and vice-versa — same guarantee orders provides.

## Migration Plan

Additive backend wiring (no schema change — reuses existing cash tables) plus a frontend polish
pass. Ship backend + frontend together. Rollback = revert the cross-module writes in the two
repositories/use cases and the frontend label/message tweaks; no data migration. Existing rows are
unaffected.

## Open Questions

- Multi-branch fiado: is the paying employee's branch always the right drawer, or should a credit
  carry/choose a branch at settlement time? Deferred to the multi-branch phase; employee-branch is
  the pragmatic single-branch answer.
- Should a future change also reflect order **refunds** or payment **voids** as compensating cash
  movements? Out of scope here; noted for a later "cash reversals" change.
