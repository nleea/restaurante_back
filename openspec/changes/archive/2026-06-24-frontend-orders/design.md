## Context

The Orders backend is complete: dining tables (`free`/`occupied`), order lifecycle (`open`/`closed`/`cancelled`), items (referencing `product_variant_id` + a client-supplied `unit_price`, with server-recomputed `line_subtotal` and order `subtotal`/`discount`/`total`), discount, close, cancel, receipts, and payments. With `menu-product-variants` shipped, the client can now discover a product's sellable variants and their derived `extra_price`. Per-branch product prices already exist (`/menu/products/{id}/prices`) and the branch context (`frontend-branch-context`) provides the active branch.

Two frontend-facing facts shape this change:
1. Every order mutation needs an `employee_id`. The order-taker roles (`cashier`, `waiter`) hold `orders.*` but **not** `staff.read`, so they cannot resolve their own employee through `GET /staff/employees` (which is gated by `staff.read`).
2. Order items carry only `product_variant_id`; labels and prices must be resolved client-side from the menu.

## Goals / Non-Goals

**Goals:**
- Let an order-taker resolve their own `employee_id` without `staff.read`.
- A usable first comandas slice: tables + open → add/edit/remove items → discount → close/cancel, for the active branch.
- Client-side price computation (`unit_price = branch price + variant.extra_price`) and item labeling.

**Non-Goals:**
- Payments / cobro (orders→cash) — a follow-up change; needs an open cash session.
- Receipts/printing, per-item cancellation, addons per line, authorization-gated cancellations.
- The KDS (kitchen) board.
- Realtime updates (polling/refetch on action is enough for the first slice).

## Decisions

### 1. Resolve the operating employee via `GET /staff/employees/me`
Add a tiny staff endpoint that returns the current user's employee, gated by authentication only (a session primitive, mirroring `GET /branches` and `POST /auth/me`). It reuses identity's `get_current_user` and a `find_employee_by_user(tenant, user_id)` repository lookup; `404` when the user is not an employee. This keeps order-takers (no `staff.read`) able to operate. **Alternative considered:** embed `employee_id` in `/auth/me`. Rejected — it couples identity to the staff module and changes a core contract; a dedicated staff endpoint is cleaner and isolated.

### 2. Client-computed item price and labels
`unit_price = Number(branchPrice(product)) + Number(variant.extra_price)`, computed when adding the item and sent to `POST /orders/{id}/items`. To label existing items (which only carry `product_variant_id`), the screen builds a **variant index** `variant_id → { productName, variantName, unitPrice }` by loading the menu's products and each product's variants (reusing `menu.loadVariants`). This mirrors how the carta loads per-branch prices (N small parallel calls; menus are small). **Alternative considered:** a server-side enriched item response — out of scope; the menu data is already on the client.

### 3. Branch-scoped, master–detail like the rest
`OrdersView` lists the active branch's open orders (master) and opens one into its ticket (detail), following the project's mobile-first master–detail pattern. Tables and "open order" live alongside. The active branch comes from the branch context; switching branches reloads. **Alternative considered:** a route per order — rejected for consistency with existing screens (single `selected` ref, no sub-routes).

### 4. Write-through refetch, server is the source of truth for totals
Every mutation (add/edit/remove item, discount, close, cancel) writes through the API, then the store refetches the order (and its items) so the **server-recomputed** subtotal/discount/total are displayed verbatim — the client never computes order totals, only the per-item `unit_price` it submits. Consistent with the menu/staff store discipline.

### 5. Scope to "take an order", defer money and kitchen
Per the design gate (small complete over large half-built), the first slice ends at close/cancel. Payments (the orders→cash integration) and KDS are separate changes with their own dependencies (open cash session; kitchen routing). Cancellation is included but only the simple form (reason + resolved employee, no authorization workflow).

## Risks / Trade-offs

- **Product with no sellable variant can't be added** → the item picker only offers products that have at least one active variant; products without variants show a hint to add one in the menu. (This is exactly why `menu-product-variants` shipped first.)
- **No price set for the active branch** → the picker disables adding that product and explains a branch price is required; mirrors the carta's "precio oculto" state.
- **Variant index is N+1 variant calls** → menus are small; calls run in parallel and are cached per product in the menu store. A future bulk endpoint can replace it.
- **Stale ticket if two devices edit the same order** → acceptable for the first slice; refetch-on-action keeps a single device consistent. Realtime is a later concern.
- **Non-employee user** → order-opening disabled with a message; read-only browsing still works.

## Migration Plan

1. Backend: `GET /staff/employees/me` (repo `find_employee_by_user`, service method, route gated by `get_current_user`), `EmployeeResponse` reused. Integration tests: resolves self; works without `staff.read`; `404` for non-employee; `401` unauthenticated. Run `ruff`/`mypy`/`pytest`.
2. Frontend: `services/orders.api.ts`; `stores/orders.ts` (currentEmployee, tables, orders, items, variant index); `views/OrdersView.vue` + components (tables, open-order, ticket with item picker); `/orders` route + "Comandas" nav. Unit tests for the store (employee resolution, price computation, write-through refetch).
3. Validate: type-check, lint, unit, build.

Rollback: the endpoint is additive; the route/nav and screen can be removed without affecting other screens.

## Open Questions

- Should the orders list also show closed/cancelled orders (with a filter), or only open? Default: open by default, with a status filter.
- Should opening a `delivery` order require a customer? Default: no for this slice (customer linkage is deferred with the customers screen).
