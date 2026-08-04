## Context

A customer's `total_spent` / `order_count` / `last_purchase_at` are stored on `CustomerModel`
(`Numeric(12,2)` default 0 / `Integer` default 0 / nullable `DateTime`) and returned by the customer
reads, but **no code ever writes them** — so they are always zero. Orders already carry a nullable
`customer_id` FK (`OrderModel.customer_id → customers.id`, `ondelete=SET NULL`), so the link exists.

The orders module already performs **close-time cross-module writes** in the same shared session,
and that's the pattern to follow:

- `OrderService.close_order` (`manage_orders.py`): `order = _require_open_order(...)` →
  `consume_inventory_for_order(...)` → `update_order(..., {status: closed, closed_at: now})` →
  `_free_table(...)`. The `_require_open_order` guard means **close only succeeds on an open order**,
  so closing twice raises a conflict.
- The orders repository already imports and writes `InventoryMovementModel`/`InventoryStockModel`
  (inventory deduction) and `CashMovementModel` (sale movement on payment) directly via
  `self._session`. Adding a `CustomerModel` import + write is consistent.
- The inventory deduction is made idempotent by a marker check (skip if `sale` movements already
  exist for the order). Customer stats have no such marker — but the **open-status guard already makes
  close exactly-once**, so the stats bump inherits exactly-once without a marker.

## Goals / Non-Goals

**Goals:**
- Populate customer purchase stats from real orders, exactly once per order, atomically with close.
- Follow the existing close-time side-effect pattern (no new infrastructure, no new endpoint).
- Surface the now-populated `last_purchase_at` on the customer detail so the data is visible.

**Non-Goals:**
- Backfilling stats for already-closed orders; decrementing on cancellation/refund; loyalty/LTV
  features; any new endpoint or permission.

## Decisions

**1. Hook on close, not on payment.** Close is the single settle event and is guarded exactly-once;
payments can be multiple (split/partial) and would risk double-counting. Semantically the stat is "a
completed purchase", which maps to close. (Also: an order has no `payment_status` — it's simply
`open`→`closed`.)

**2. Bump the stats atomically with the status flip, in one commit.** Rather than a separate
committed write (which could leave stats bumped without the close, or vice-versa, on a mid-failure
retry), the repository's close write sets `status`/`closed_at` **and** — when `customer_id` is set —
issues an atomic `UPDATE customers SET total_spent = total_spent + :total, order_count = order_count +
1, last_purchase_at = :closed_at WHERE id = :customer_id AND tenant_id = :tenant` in the same
transaction, then commits once. The increment is a SQL column expression (not read-modify-write), so
it is safe under concurrency. Replaces the current `update_order(..., {status, closed_at})` call in
`close_order` with a close method that takes `customer_id`, `total`, and `closed_at`.

**3. Exactly-once via the open-status guard.** No stats marker is needed: `_require_open_order`
ensures the order is open when close runs, and the close flips it to `closed`; a second close raises
a conflict before any write. So the stats bump fires exactly once per order. The spec's
"not double-counted" scenario rests on this.

**4. Null customer is a no-op.** `customer_id` is nullable; the close method skips the customer
update when it is null. No error, no write.

**5. Port + adapter.** The repository port (`orders/domain/ports.py`) gains the new close signature
so mypy/strict typing stays sound (as the cash-integration change did for its new methods). The
orders repository imports `CustomerModel` from the customers module's infrastructure models.

**6. Frontend is a one-field reveal.** `Customer` already carries `total_spent`/`order_count`/
`last_purchase_at`; the customer detail shows the first two. Add `last_purchase_at` ("última compra",
formatted, or "—" when null). No store/service change. The values stop being zero once the backend
ships and orders are closed.

## Risks / Trade-offs

- **Mid-close failure between commits** (inventory commit, then close+stats commit) → if the close+
  stats commit fails, inventory was deducted but the order stays open and stats unchanged; a retry
  re-runs (inventory skips via its marker, stats bump on the now-still-open order). → Net exactly-once
  for stats; matches the existing inventory-deduction looseness.
- **`total` mutability** — the stat uses the order `total` at close time. If items change after close
  (they can't — close is terminal) this would drift; since close is terminal, the total is final. →
  Safe.
- **No backfill** — historical closed orders won't retroactively populate stats. → Acceptable;
  forward-looking. Noted, not hidden.
- **Cancellation/refund don't decrement** — out of scope; a future "reversals" change could handle
  it, consistent with the deferred cash-reversals note.

## Migration Plan

Additive backend wiring (no schema change — the stat columns and the FK already exist) plus a
one-field frontend reveal. Ship backend + frontend together. Rollback = revert the close write change
(and its port), and the customer-detail field; no data migration. Existing closed orders are
unaffected either way.

## Open Questions

- Should a later change backfill stats from already-closed orders (a one-off recompute)? Deferred —
  this change is forward-looking; a recompute script is a separate, optional task.
- Should cancellation/refund decrement stats? Out of scope; folds naturally into a future
  cash/stat "reversals" change.
