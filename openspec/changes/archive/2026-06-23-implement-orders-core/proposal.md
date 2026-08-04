## Why

Orders (comandas) is the **operational core** of the product — the backbone a waiter uses every shift. It connects tables, products (variants), kitchen, delivery and cash, and is what makes the pilot restaurants able to take and track service without paper. The module exists today only as a data layer (7 tables) with no functional layer. With `menu`, `staff`, `inventory` and `recipes` already live, the order lifecycle can be built now. Two parts that hard-depend on still-unbuilt modules are deliberately deferred: **payments** (require `cash_sessions` from the unbuilt `cash` module) and **inventory deduction via recipes** (a focused integration change, to keep this one a small, complete system).

## What Changes

- Add the **application + API layer** for the orders module's core lifecycle, mirroring the `menu`/`staff`/`inventory`/`recipes` reference modules (hexagonal).
- **Dining tables**: CRUD plus a status field (`free`/`occupied`), unique table number per branch.
- **Orders (comandas)**: open an order on a channel (`dine_in`/`takeaway`/`delivery`) with a serving employee and optional dining table / customer; list orders (filter by status, table); get an order with its items and addons.
- **Order items**: add a product variant line (quantity + unit-price snapshot), update quantity, remove a line; attach/detach addons to a line. Each write **recomputes the order's `subtotal` / `total`** (line subtotals + addon prices − order discount).
- **Discounts**: set an order-level discount (clamped to ≥0 and ≤ subtotal).
- **Cancellations**: cancel a whole order or a single item with a reason, recording a `cancellations` audit row (who requested, whether authorization was required); cancelling frees the table.
- **Receipt prints**: record a `receipt_prints` audit row (first print vs reprint).
- **Lifecycle**: order `open → closed` (close stamps `closed_at` and frees the table) or `open → cancelled`. Items default to `pending`; full KDS state transitions belong to the `kitchen` module.
- Enforce **multi-tenant + multi-branch isolation** (tenant from middleware; `branch_id` validated against the tenant) and **RBAC** with the existing `orders.read` / `orders.create` / `orders.update` / `orders.cancel` permissions.
- Register the new router in `main.py`.

### Explicitly out of scope (deferred)
- **Payments** (`order_payments`, `orders.pay`) — needs `cash_sessions` from the unbuilt `cash` module. Future change after `cash`.
- **Inventory deduction via recipes** — when an order closes, deduct ingredients through the BOM. Future change `integrate-orders-inventory` (needs a non-blocking sale-consumption path in `inventory`).
- **Customer / WhatsApp linking** beyond accepting an optional id (modules `customers` / `messaging` not built; FKs are nullable so ids are simply optional).

## Capabilities

### New Capabilities
- `order-management`: Dining tables and the full order lifecycle (open, add/update/remove items and addons, discounts, totals, cancellations, receipts, close) — tenant/branch-isolated and RBAC-protected. Payments and inventory deduction are out of scope.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/orders/`: `domain/ports.py`, `application/use_cases/manage_orders.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`.
- **Modified**: `src/restaurante/main.py` (include `orders_router`).
- **Depends on** existing tables `product_variants` (menu, data-only), `addons` (menu), `employees` (staff), `branches`, plus optional `customers`/`whatsapp_contacts` — validated for existence where required.
- **Reused**: `shared/api/deps.get_tenant_id`, `shared/database.get_session`, tenant auto-filter, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`).
- **APIs**: new `/orders/*` endpoints (orders, items, cancellations, receipts) and `/orders/tables` (or `/dining-tables`). No breaking changes.
- **Tests**: new integration suite under `tests/modules/orders/` (sqlite, FK enforcement) — seeds product variants/addons directly (menu has no variant API yet).
