## Context

The `kitchen` module has ORM models (`kitchen_stations`, `product_stations`, `order_item_stations`) and domain dataclasses but no functional layer. `menu`, `orders`, `inventory`, `recipes`, `cash` are implemented; `orders` is the operational core this consumes. Constraints from `CLAUDE.md`: hexagonal layering, row-level multi-tenancy, multi-branch via `branch_id`, English-only identifiers, "small complete system".

Facts confirmed in code:
- `kitchen_stations` (branch-scoped): `name`, `position`, `is_active`.
- `product_stations` (tenant-scoped): bridge `product_id` → `kitchen_station_id`, unique on the pair. Keyed by **product**, not variant.
- `order_item_stations` (branch-scoped): `order_item_id`, `kitchen_station_id`, `status` (`pending` default), `entered_at` (server-defaulted), `ready_at`.
- `order_items` carry `product_variant_id`, `quantity`, `status` (`cancelled` excluded). To route, resolve `order_item.product_variant_id → product_variants.product_id → product_stations`.
- Permissions `kitchen.read` / `kitchen.update` already exist; the base `kitchen` role has `orders.read` + both.
- `kitchen` is registered in `models_registry.py`; tables exist in migration `0002`. Shared `ValidationError` (→422) exists.

## Goals / Non-Goals

**Goals:**
- Domain ports, application service, SQLAlchemy repository, and API router for: stations CRUD; product→station routing config; routing an order's items into tickets; the KDS board with a `pending → in_progress → ready` lifecycle.
- Tenant/branch isolation, cross-module reference validation, RBAC.
- Integration tests (sqlite, FK enforcement).

**Non-Goals (deferred):**
- Auto-routing on order item add (kept an explicit action to decouple `orders`/`kitchen`).
- Reflecting KDS readiness back into the order item's `orders` status.
- Prep-time SLA metrics/alerts (timestamps captured for later reporting).
- Station load balancing / multi-station "any one of" routing logic — every configured station gets a ticket.

## Decisions

**1. Mirror the established module layout; one `KitchenService`.**
`domain/ports.py` (`KitchenRepository` Protocol), `application/use_cases/manage_kitchen.py` (`KitchenService`), `infrastructure/repositories.py` (`SqlAlchemyKitchenRepository`), `infrastructure/api/{deps,schemas,router}.py`. Rationale: consistency with six working references.

**2. Routing is an explicit "send to kitchen" action owned by the kitchen module.**
`POST /kitchen/orders/{order_id}/route` reads the order's non-cancelled items (orders tables) and product-station config, then creates tickets. The kitchen repository imports orders/menu models (same cross-module pattern used by orders↔cash/inventory). Rationale: keeps `orders` unaware of `kitchen`; the waiter's "send" is a deliberate step. Alternative (auto-route on add) rejected for coupling.

**3. Routing resolves variant → product → stations, and is idempotent.**
For each non-cancelled item: `product_variant.product_id` → all `product_stations` → one `order_item_stations` per (item, station) not already present. No station for the product ⇒ no ticket. Idempotency via an existence check on (order_item_id, kitchen_station_id). Rationale: re-sending an order (e.g. after adding items) must not duplicate existing tickets; matches the inventory-deduction idempotency approach.

**4. Ticket lifecycle is a strict forward state machine.**
`advance_ticket`: `pending → in_progress → ready`; `ready` is terminal (advancing it → `ConflictError`); `ready_at` stamped on the `ready` transition. Rationale: a KDS only moves forward; explicit guard prevents accidental regressions. (A separate "recall" is out of scope.)

**5. Validation split: Pydantic for shape, service for cross-entity rules.**
Pydantic: required fields, position int, optional status filter. Service: reference existence (branch/product/station/order) in tenant, duplicate-mapping guard, lifecycle guard. Errors reuse `shared/domain/errors`.

**6. Stations are branch-scoped; product→station config is tenant-scoped.**
Matches the models: a station belongs to a branch, but a product's routing config is the same across branches (tenant-level). Tickets are branch-scoped (created at the order's branch). Rationale: follow the data model's deliberate scoping.

## Risks / Trade-offs

- **Product-station config is tenant-wide but stations are per-branch** → a product could be mapped to a station from another branch; routing creates tickets at the order's branch regardless. Mitigation: validate the station exists in the tenant; cross-branch station mapping is an admin error surfaced by the board being empty. Acceptable at pilot scale (one branch).
- **Re-routing after adding items** creates only the new tickets (idempotent) but does not remove tickets for later-cancelled items → acceptable; a cancelled item's ticket can be ignored on the board (or a future change can void it).
- **No back-link to order status** means "all items ready" isn't reflected in `orders` → intended; cross-module status sync is a separate concern.
- **sqlite vs Postgres** → enum-as-string statuses and FK/unique constraints behave consistently; FK enforcement enabled in tests.

## Migration Plan

1. No schema change — all three tables exist in migration `0002`. Autogenerate should be a no-op for kitchen (verify statically if Postgres unavailable).
2. Deploy is additive — new `/kitchen` endpoints, router in `main.py`. Reverting removes them.

## Open Questions

- Should routing be auto-triggered when an order is closed or when items are added, instead of an explicit call? (Default: explicit `route` action now.)
- Should a ticket support a `served`/`recalled` state beyond `ready`? (Default: stop at `ready`.)
- Should marking all of an order's tickets `ready` flip the order item's `orders`-side status? (Default: no; out of scope.)
