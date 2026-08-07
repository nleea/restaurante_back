## Context

`recipes` (BOM), `inventory` (stock + movement ledger) and `orders` (core + cobro) are all implemented. The missing seam is consumption-on-sale. This change makes closing an order deduct ingredients via the variant's recipe. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English-only identifiers, "small complete system". The user chose **automatic deduction on close** and **non-blocking (negative-allowed)** consumption.

Facts confirmed in code:
- `recipe_items` (recipes): `product_variant_id`, `ingredient_id`, `quantity`, `unit_of_measure_id`. Listable per variant.
- `inventory_stocks` (branch-scoped): `ingredient_id`, `branch_id`, `current_quantity`, `min_stock`. `inventory_movements`: `ingredient_id`, `type`, `reason`, `quantity`, `employee_id`, `reference_id`, `notes`.
- Inventory's **repository** `apply_movement(movement, delta)` updates the stock row by `delta` and inserts the movement, committing once — and does NOT enforce the no-negative rule (that guard lives only in the inventory *service* `register_movement`). So a sale deduction that must allow negative naturally uses the same low-level pattern.
- `order_items` carry `product_variant_id`, `quantity`, `status` (cancelled items excluded). The order carries `branch_id` and `employee_id`.
- The orders repository already reaches into other modules' models (menu, cash); adding recipes + inventory reads/writes is the same established pattern.
- Closing is one-shot (an order cannot be re-closed — guarded in `OrderService.close_order`).

## Goals / Non-Goals

**Goals:**
- On close, deduct each non-cancelled item's recipe ingredients (`recipe_qty × item_qty`) from inventory at the order's branch, recording `out`/`sale` movements referencing the order.
- Non-blocking: never fail the close for insufficient stock; allow negative on-hand.
- Idempotent: never double-deduct an order.
- No changes to recipes' or inventory's public APIs.
- Extend the orders test suite.

**Non-Goals:**
- Unit conversion (recipe-line unit assumed equal to ingredient stock unit; recipes already deferred conversions).
- Costing/margin (needs purchasing costs).
- Reversing consumption (orders cannot be reopened).
- Deducting on any trigger other than close.

## Decisions

**1. Deduction is orchestrated by `OrderService.close_order`, executed by one repository method.**
`OrdersRepository.consume_inventory_for_order(tenant_id, order_id)` performs the whole deduction (read items → read each variant's recipe → upsert stock + insert movement per ingredient) in a **single transaction/commit**, then `close_order` marks the order closed and frees the table. Rationale: keeping the multi-row deduction atomic in one repo method avoids half-deducted orders; orchestrating from the existing close keeps the trigger automatic and the service decoupled from recipes/inventory internals.

**2. The orders repository owns the cross-module deduction (consistent with existing pattern).**
It already imports menu and cash models; it will import `RecipeItemModel`, `InventoryStockModel`, `InventoryMovementModel`. Rationale: orders is the higher-level consumer; a dedicated cross-module "consumption service" would add a layer for no benefit at this scale. Recipes/inventory keep their own APIs untouched.

**3. Negative-allowed: deduct via a direct stock decrement, bypassing the over-draw guard.**
The deduction decrements `current_quantity` by the consumed amount even below zero, and records the `out` movement (magnitude in `quantity`, direction in `type`), exactly mirroring inventory's own `apply_movement` semantics. Rationale: the sale already happened; blocking the close would be operationally wrong. Negative on-hand surfaces a discrepancy that the existing recount flow corrects. The inventory *service* over-draw guard remains for manual `out` movements; only the sale path bypasses it, deliberately.

**4. Idempotency via existing `sale` movements for the order.**
`consume_inventory_for_order` first checks whether any `inventory_movements` with `reference_id = order_id` and `reason = 'sale'` exist; if so it is a no-op. Rationale: defends against any retry; complements the close-once guard.

**5. Stock row auto-created if missing.**
If an ingredient has no stock row at the branch, deduction creates it with `current_quantity = −consumed` (negative), matching inventory's first-movement-creates-row behavior. Rationale: a branch may sell before any purchase was recorded; the negative row flags it.

**6. Employee + branch come from the order.**
Movements are attributed to `order.employee_id` (a valid tenant employee) at `order.branch_id`. Rationale: no separate actor resolution; the order already carries both.

## Risks / Trade-offs

- **Unit mismatch** (recipe line unit ≠ ingredient stock unit) deducts the raw number without conversion → documented limitation; correct once costing/conversion is built. The `units_of_measure` table already carries conversion data for later.
- **Close now does more work** (reads recipes, writes movements) inside one transaction → fine at order sizes; correctness over micro-optimization.
- **Partial failure between deduction-commit and close-commit**: deduction commits first; if the subsequent close update fails, the order stays open with `sale` movements recorded — a retry of close is a no-op for deduction (idempotent) and proceeds to close. Acceptable and self-healing.
- **Negative stock** can accumulate if recounts are neglected → by design a visible signal, not a silent error.
- **sqlite vs Postgres** → `Numeric`/`Integer` arithmetic and FK behavior consistent; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — all tables exist in migration `0002`. Autogenerate should be a no-op; verify statically if Postgres unavailable.
2. Behavioral, additive deploy — `close` gains a side effect; no API signature change. Reverting the code restores close-without-deduction.

## Open Questions

- Should closing be blocked (or warned) when deduction would push critical ingredients deeply negative? (Default: never block; rely on recount + low-stock view.)
- Where should `reason` strings live (a shared enum)? (Default: literal `'sale'` for now, matching inventory's free-string `reason`.)
- Should a future "reopen order" reverse consumption? (Out of scope; orders are not reopenable today.)
