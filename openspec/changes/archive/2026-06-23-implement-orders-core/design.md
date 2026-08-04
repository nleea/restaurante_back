## Context

Orders is the operational core and the largest module so far (7 tables: `dining_tables`, `orders`, `order_items`, `order_item_addons`, `order_payments`, `cancellations`, `receipt_prints`). The `menu`/`staff`/`inventory`/`recipes` modules are the established hexagonal reference. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English-only identifiers, and "prefer a small complete system over a large half-built one".

Facts confirmed in code:
- Most order tables are branch-scoped (`BranchScopedMixin`); `order_item_addons` is tenant-scoped (it hangs off an item which fixes the branch).
- `order_payments.cash_session_id` is **NOT nullable** and references `cash_sessions` — owned by the **unbuilt** `cash` module. Payments therefore cannot be implemented now.
- `orders` references `employees` (staff ✅), optional `customers` / `whatsapp_contacts` (unbuilt; nullable), and `dining_tables` (own). `order_items` references `product_variants` (menu, data-only). `order_item_addons` references `addons` (menu ✅).
- Permissions `orders.read` / `orders.create` / `orders.update` / `orders.cancel` / `orders.pay` already exist in the catalog.
- Entities already follow the project convention (business fields first, `id` optional).
- `orders` is registered in `models_registry.py`; tables exist in migration `0002`. Shared `ValidationError` (→422) exists.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, and API router for the order lifecycle, mirroring the reference modules.
- Dining-table CRUD + status; order open/get/list; item add/update/remove; addon attach/detach; total recomputation; order-level discount; cancellations (order + item); close; receipt-print log.
- Tenant/branch isolation, cross-module reference validation, RBAC.
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred to follow-up changes):**
- **Payments** (`order_payments`, `orders.pay`) — blocked on `cash`. Future change after `cash` is built.
- **Inventory deduction via recipes** on close — future `integrate-orders-inventory` change (needs a non-blocking sale-consumption path in `inventory`).
- **KDS item-state transitions** beyond the default `pending` and the `cancelled` terminal state — belong to the `kitchen` module.
- Customer/WhatsApp management — only an optional id is accepted (nullable FK).

## Decisions

**1. Mirror the `inventory` module layout; one cohesive `OrderService`.**
`domain/ports.py` (`OrdersRepository` Protocol), `application/use_cases/manage_orders.py` (`OrderService`), `infrastructure/repositories.py` (`SqlAlchemyOrdersRepository`), `infrastructure/api/{deps,schemas,router}.py`. Despite many entities, a single service keeps the lifecycle rules in one place (totals, status guards). Rationale: consistency; the entities form one aggregate around `Order`.

**2. `Order` is the consistency boundary; totals are recomputed server-side, never trusted from the client.**
Every mutation of items/addons/discount recomputes `subtotal = Σ line_subtotal` and `total = subtotal − discount` inside the same transaction as the mutation. `line_subtotal = unit_price × quantity + Σ addon.applied_price`. Rationale: the client must not be able to desync money fields; the order row is the single source of truth.

**3. Price snapshots are captured at write time.**
`order_items.unit_price` and `order_item_addons.applied_price` are stored when the line is created (snapshot), not looked up live later. For this change the API accepts `unit_price` explicitly (a later change can default it from `menu` per-branch prices). Rationale: an order must reflect the price at the moment of sale even if the catalog price later changes; matches how `menu` keeps prices per branch.

**4. Status guards enforce the lifecycle.**
Mutations (add/update/remove item, attach/detach addon, set discount, cancel, close) require the order to be `open`; otherwise `ConflictError`. `close` → `closed` + `closed_at` + free table; `cancel` (order) → `cancelled` + free table. Item `status` defaults `pending`; cancelling an item sets it `cancelled`. Rationale: explicit state machine prevents editing settled orders.

**5. Table status side-effects are handled by the service.**
Opening a dine-in order on a table sets the table `occupied`; closing/cancelling the order frees it. Kept in the service (not the DB) so the rule is visible and testable. Concurrency on table status is acceptable at pilot scale (one POS/branch).

**6. Validation split: Pydantic for shape, service for cross-entity/business rules.**
Pydantic: channel is a `Literal`, quantity `> 0`, prices/discount `≥ 0`, required fields. Service: reference existence (employee/branch/table/variant/addon) in tenant, status guards, discount ≤ subtotal, table-belongs-to-branch. Errors reuse `shared/domain/errors`.

**7. Cancellation authorization is recorded, not enforced (yet).**
`cancellations.requires_authorization` and `authorized_by_employee_id` are captured as audit data; this change does not gate cancellation behind a second approver (no approval workflow module yet). Rationale: keep scope tight; the audit columns are populated for a future authorization flow.

## Risks / Trade-offs

- **Many endpoints / surface area** → mitigate by grouping into one router with clear sub-sections and reusing the established patterns; tests cover the lifecycle end to end.
- **Totals recomputation cost** (re-reads items per mutation) → negligible at order sizes; correctness over micro-optimization.
- **Deferred payments/deduction means an order can be `closed` without money or stock effects** → explicitly documented; closing is a lifecycle state, and the money/stock integrations land in their own changes once `cash` exists and the deduction path is added. This is the "small complete system" trade-off the user approved.
- **sqlite vs Postgres** → `Numeric`/`Integer` arithmetic and FK/unique constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change expected — all 7 tables exist in migration `0002`. After implementation, an `alembic revision --autogenerate` should be a no-op for orders (live run needs Postgres; otherwise verify statically).
2. Deploy is additive — new `/orders` endpoints, router included in `main.py`. Reverting the code removes the endpoints.

## Open Questions

- Endpoint path for tables: nest under `/orders/tables` vs a top-level `/dining-tables`? (Default: `/orders/tables` to keep the module's surface under one prefix.)
- Should `unit_price` be auto-filled from `menu` per-branch prices instead of client-supplied? (Default: client-supplied now; auto-fill when the orders↔menu pricing integration is scoped.)
- Should closing require at least one item? (Default: no — allow closing an empty order as a cancellation-like no-op; revisit with payments.)
