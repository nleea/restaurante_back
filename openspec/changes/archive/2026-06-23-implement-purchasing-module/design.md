## Context

The `purchasing` module has 7 ORM tables and domain dataclasses but no functional layer. It is the supply side of inventory (the consumption side, orders→inventory, is done). `recipes` (ingredients), `inventory`, `staff`, and `catalog` (`units_of_measure`) are all available. The user chose the **full procure-to-pay** scope. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English identifiers, "small complete system" (here applied per-flow within one cohesive module).

Facts confirmed in code:
- `suppliers`, `supplier_ingredients`, `purchase_request_items`, `purchase_order_items`, `purchase_payments` are tenant-scoped; `purchase_requests` and `purchase_orders` are branch-scoped (operational documents).
- `purchase_orders.purchase_request_id` is **NOT nullable** → an order must come from a request; the request flow is mandatory.
- `purchase_order_items` carry `ordered_quantity`, `received_quantity` (default 0), `unit_price`, `unit`. `purchase_payments` has **no** `cash_sessions` link → purchase payments are independent of the POS drawer.
- Cross-module FKs: `ingredients` (recipes), `units_of_measure` (catalog), `employees` (staff). All exist.
- Permissions `purchasing.read` / `purchasing.manage` / `purchasing.approve` exist.
- Entities currently violate the convention (`id` and timestamps required) → restructure needed.
- Inventory's repository pattern (used by orders→inventory) writes `inventory_movements` + updates `inventory_stocks` directly; the purchasing repo reuses the same approach for goods receipt.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, API router for: suppliers; supplier ingredients; purchase requests + approval; purchase orders (total computed); goods receipt feeding inventory; purchase payments.
- Tenant/branch isolation, cross-module reference validation, RBAC split (read/manage/approve).
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred):**
- Linking purchase payments to a POS cash session (`cash` `out` movement).
- Costing / weighted-average ingredient cost from purchase prices.
- Unit conversion between purchase and stock units (assumed equal).
- Editing/cancelling issued orders or reversing receipts.

## Decisions

**1. Mirror the established layout; one `PurchasingService`.**
`domain/ports.py` (`PurchasingRepository`), `application/use_cases/manage_purchasing.py` (`PurchasingService`), `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`. One service holds the procure-to-pay rules; the tables form one aggregate cluster around suppliers and orders.

**2. Documents are created with their line items in one call; money/quantities are derived server-side.**
A request is created with its items; an order with its items, and the order `total` is computed (`Σ ordered_quantity × unit_price`), never trusted from the client. Rationale: documents are atomic and totals must be authoritative.

**3. Mandatory request → approval → order chain.**
Because `purchase_orders.purchase_request_id` is non-nullable, an order can only be created from an `approved` request (guard → `ConflictError` otherwise). Approval/rejection is a separate permission (`purchasing.approve`) and only valid from `pending`. Rationale: the data model encodes an authorization workflow; honor it.

**4. Goods receipt is the inventory integration; receiving writes inventory directly.**
`receive_items` takes a per-item received quantity (a delta for this receipt), and for each: increments `received_quantity`, inserts an `inventory_movements` (`in`, reason `purchase`, `reference_id = order_id`, `employee_id = received_by`), and increases the `inventory_stocks` row (creating it if missing) — all in one transaction. The PO status is recomputed: `received` if every item reached its ordered quantity, else `partially_received`. Rationale: receiving is the whole point (stock in); deltas allow multiple partial receipts without double-counting; mirrors the orders→inventory write pattern.

**5. Payment status derived from the sum of payments vs total.**
Registering a payment inserts a `purchase_payments` row and recomputes `payment_status`: `paid` (Σ ≥ total), `partial` (0 < Σ < total), else `pending`. No cash-session coupling. Rationale: purchases are often paid outside the POS drawer; keep independent (a future change can link to cash).

**6. Validation split: Pydantic for shape, service for business rules.**
Pydantic: positive quantities/prices, non-empty item lists, required fields. Service: reference existence (supplier/ingredient/unit/employee/branch) in tenant, uniqueness (supplier-ingredient), state guards (approve from pending; order from approved request), receipt/payment math. Errors reuse `shared/domain/errors`.

## Risks / Trade-offs

- **Large surface (7 tables, ~6 flows)** → mitigated by one cohesive service/router and the established patterns; tests cover request→order→receive→pay end to end. Still the biggest module.
- **Goods receipt allows over-receipt** (received > ordered) unless guarded → decision: allow received to exceed ordered (suppliers sometimes deliver extra); status uses "≥ ordered" for `received`. Surfaced as an open question.
- **No unit conversion** → purchase unit assumed equal to stock unit; documented, consistent with the rest of the system.
- **Purchase payment not reflected in cash** → intentional; finance/cash linkage is a later concern.
- **sqlite vs Postgres** → `Numeric` arithmetic, FK and unique constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — all 7 tables exist in migration `0002`. Autogenerate should be a no-op (verify statically if Postgres unavailable).
2. Deploy is additive — new `/purchasing` endpoints, router in `main.py`. Reverting removes them.

## Open Questions

- Should goods receipt reject over-receipt (received > ordered), or allow it (current default: allow)?
- Should approving a request auto-create a draft order? (Default: no; order creation is explicit.)
- Should purchase payments optionally post a cash `out` movement when paid from the drawer? (Default: out of scope.)
