## Why

Purchasing closes the supply side of inventory. Today stock only goes **down** (sales deduct via recipes); there is no controlled way to bring stock **in**. Restaurants need suppliers, purchase requests, purchase orders, goods receipt, and supplier payments — and receiving goods must increase real inventory. This is also the foundation for true costing (purchase prices feed ingredient cost). The module exists only as a data layer (7 tables). With `recipes` (ingredients), `inventory`, `staff` and `catalog` units all available, the full procure-to-pay flow can be built now.

## What Changes

- Add the **application + API layer** for the purchasing module (hexagonal), covering the full procure-to-pay flow.
- **Suppliers**: CRUD (name, tax id, contact, active flag).
- **Supplier ingredients**: which ingredients a supplier provides, with a reference price and unit (attach/detach/list).
- **Purchase requests** (branch documents): create with line items (ingredient, requested quantity, unit), list/get; **approve** or **reject** (status `pending → approved | rejected`, recording the approver) — gated by `purchasing.approve`.
- **Purchase orders**: create from an **approved** request, for a supplier, with line items (ingredient, ordered quantity, unit price, unit); the order `total` is computed server-side. List/get with items.
- **Goods receipt**: record received quantities per order item; each receipt **generates an inventory `in` movement** (reason `purchase`, referencing the PO) at the branch and increases on-hand. The PO status advances `created → partially_received → received`.
- **Purchase payments**: register payments against a PO (amount, method, employee); `payment_status` advances `pending → partial → paid` from the sum of payments vs the order total. Purchase payments are independent of the POS cash drawer (no `cash_sessions` link).
- Enforce **multi-tenant + multi-branch isolation** and **RBAC**: `purchasing.read` (reads), `purchasing.manage` (suppliers, catalog, requests, orders, receipt, payments), `purchasing.approve` (approve/reject requests).
- Register the new router in `main.py`.
- No ORM model changes expected — tables and the `purchasing` registration already exist; entities are restructured to the project convention (business fields first, `id`/timestamps optional).

### Explicitly out of scope (deferred)
- **Paying a purchase from the POS cash drawer** (creating a cash `out` movement) — `purchase_payments` is standalone here; a future change could link it to a cash session.
- **Costing / weighted-average cost** updates to ingredients from purchase prices — a later change (prices are captured on order items and supplier ingredients for it).
- **Unit conversion** between purchase unit and stock unit — assumed equal (consistent with recipes/inventory).

## Capabilities

### New Capabilities
- `purchasing-management`: Procure-to-pay — suppliers and their ingredient catalog, purchase requests with approval, purchase orders, goods receipt that feeds inventory, and supplier payments. Tenant/branch-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/purchasing/`: `domain/ports.py`, `application/use_cases/manage_purchasing.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; restructure `domain/entities.py` to the convention.
- **Modified**: `src/restaurante/main.py` (include `purchasing_router`).
- **Cross-module reads/writes**: the purchasing repository reads `ingredients` (recipes), `units_of_measure` (catalog), `employees` (staff), and on receipt writes `inventory_movements` + updates `inventory_stocks` (inventory). No change to those modules' APIs.
- **Reused**: tenant middleware, `shared/database.get_session`, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`), RBAC `require_permission`.
- **APIs**: new `/purchasing/*` endpoints (suppliers, supplier-ingredients, requests, orders, receipt, payments). No breaking changes.
- **Closes the inventory loop**: stock now increases via goods receipt and decreases via sales.
- **Tests**: new integration suite under `tests/modules/purchasing/` (sqlite, FK enforcement) — seeds ingredients/units/employees directly.
