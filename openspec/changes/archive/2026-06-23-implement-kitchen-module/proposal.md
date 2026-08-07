## Why

Kitchen (KDS — kitchen display system) is what turns a comanda into prepared food on the line. Today an order item only has a coarse `pending`/`cancelled` status; there is no way to route a dish to the station that cooks it, nor for cooks to see and advance their queue. The module exists only as a data layer (`kitchen_stations`, `product_stations`, `order_item_stations`). With `menu` (products/variants) and `orders` (items) implemented, the KDS can be built now, completing the in-restaurant service flow: **take order → route to stations → cook → mark ready**.

## What Changes

- Add the **application + API layer** for the kitchen module, mirroring the reference modules (hexagonal).
- **Kitchen stations**: CRUD for a branch's stations (name, display position, active flag).
- **Product → station routing config**: map which station(s) prepare a given product (attach/detach, list a product's stations).
- **Route an order to the kitchen**: an action that, for each non-cancelled order item, resolves its product (via the item's product variant) and creates an `order_item_stations` ticket per configured station, in state `pending`. Items whose product has no station produce no ticket; routing is **idempotent** (an item already routed to a station is not duplicated).
- **KDS board + lifecycle**: list a station's tickets (optionally filtered by state) and advance a ticket `pending → in_progress → ready` (stamping `ready_at` on ready). Regressing or advancing a `ready` ticket is rejected.
- Enforce **multi-tenant + multi-branch isolation** (tenant from middleware; `branch_id` validated against the tenant) and **RBAC** using the existing `kitchen.read` (board/reads) and `kitchen.update` (stations, routing, advancing) permissions.
- Register the new router in `main.py`.
- No ORM model changes expected — tables and the `kitchen` registration already exist (entities get a minor tidy: `OrderItemStation.entered_at` becomes optional/server-defaulted).

### Explicitly out of scope (deferred)
- **Automatic routing when items are added** to an order — routing here is an explicit "send to kitchen" action to keep `orders` and `kitchen` decoupled. A future change could auto-route on item add.
- **Bumping the order item's own status** in `orders` when all its tickets are ready — kept separate; the KDS tracks its own per-station state.
- **Time/SLA metrics** (prep duration alerts) — `entered_at`/`ready_at` are captured for a later reporting change.

## Capabilities

### New Capabilities
- `kitchen-management`: Kitchen stations, product→station routing, sending an order's items to the line as tickets, and the KDS board with a `pending → in_progress → ready` lifecycle. Tenant/branch-isolated and RBAC-protected.

### Modified Capabilities
<!-- None — no existing spec's requirements change. -->

## Impact

- **New code** under `src/restaurante/modules/kitchen/`: `domain/ports.py`, `application/use_cases/manage_kitchen.py`, `infrastructure/repositories.py`, `infrastructure/api/{deps,schemas,router}.py`; minor restructure of `domain/entities.py` (`entered_at` optional).
- **Modified**: `src/restaurante/main.py` (include `kitchen_router`).
- **Depends on** existing tables `products` and `product_variants` (menu), `order_items` (orders), `branches` — validated for existence; and the identity RBAC `require_permission` dependency.
- **Reused**: `shared/api/deps.get_tenant_id`, `shared/database.get_session`, tenant auto-filter, `shared/domain/errors` (`NotFoundError`, `ConflictError`, `ValidationError`).
- **APIs**: new `/kitchen/*` endpoints (stations, product routing config, order routing, station board, advance). No breaking changes.
- **Tests**: new integration suite under `tests/modules/kitchen/` (sqlite, FK enforcement) — seeds products/variants and order items directly.
