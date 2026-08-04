## Why

The public storefront at `/store` is fully built but entirely mock: it renders a hardcoded carta
themed by `mockPublishedConfig`, and its checkout confirms nothing. Meanwhile the admin now has a
persisted appearance config (Fase 2) and a real menu. This change makes `/store` render the **real**
menu of the tenant, themed by the **saved** appearance config, and lets a customer place a **real
order** that lands in the kitchen/dispatch flow — closing the loop from "admin configures" to
"customer orders".

## What Changes

- **Public storefront API** (unauthenticated, tenant resolved by subdomain like `/auth/login`):
  - `GET /storefront/appearance` — the saved appearance config (or default), no `menu.read` gate.
  - `GET /storefront/menu` — a public read-model: active categories, active/sellable products with
    their primary-branch price, image, description, the product's sellable variant id, available
    addons, and the recipe-derived removable ingredients (already filtered by `is_customer_removable`).
    Only customer-safe fields — no cost, no BOM quantities.
  - `POST /storefront/orders` — create a real order from a cart: require name + phone, find-or-create
    the customer by phone, open an order on the tenant's system employee with channel `takeaway`
    (pickup) or `delivery`, record the chosen payment method as an intent (`orders.payment_method`),
    add each line with its addons and a kitchen note (chosen removals folded in), and attach a
    delivery (address / GPS) when applicable. The order lands **pending** (items NOT auto-fired —
    staff confirm and fire). Returns an order number + initial status.
- **Frontend `/store` goes live**:
  - Fetch the appearance config + menu from the public API (loading/empty states); theme still
    applied as CSS variables from the fetched config.
  - Map the public menu into the existing `StorefrontProduct`/`Addon` types; the product detail
    shows real addons and real removable ingredients.
  - The checkout (cart → fulfillment → payment → summary) submits to `POST /storefront/orders`;
    confirmation shows the real order number and status.
- **System employee** for web orders: each tenant lazily gets a "Pedidos web" employee so the
  NOT-NULL `orders.employee_id` is satisfied without schema changes or a logged-in user.

## Capabilities

### New Capabilities
- `storefront-public-api`: public, subdomain-scoped, no-auth endpoints that serve the appearance
  config and a customer-safe menu read-model, and accept a storefront order (composing customer +
  order + items + addons + delivery in one transaction on a system employee).
- `frontend-storefront`: the `/store` view consuming the public API — real config theming, real
  menu browse + product detail (real addons + recipe-derived removables), and a checkout that
  places a real order.

### Modified Capabilities
- `order-management`: orders gain a nullable `payment_method` intent column (recording a customer's
  chosen method without creating an `order_payments` row); storefront orders land pending like any
  not-yet-fired order.

## Impact

- **Backend** (`../backend`): a new public `storefront` router/module composing existing menu,
  recipes, orders, customers, and delivery use cases; a helper to resolve-or-create the per-tenant
  system employee; a customer find-or-create-by-phone path; a menu read-model assembler
  (products + prices + addons + removable ingredient names + sellable variant id). One small
  migration adds `orders.payment_method` (nullable). No new tables; the system employee reuses
  `employees`.
- **Frontend** (`front/src`): `services/storefront.api.ts` (getAppearance/getMenu/createOrder);
  `StorefrontView` + `stores/cart` wired to real data; mocks (`mock/storefront.ts`) removed from the
  live path. Public route unchanged (`meta.public`).
- **Security note**: these endpoints are public by design (a customer isn't logged in). Abuse
  controls (rate limiting, captcha, spam orders) are acknowledged and deferred; the created order is
  `open`/unpaid and requires staff confirmation before it closes.
- Out of scope: real payment capture/gateway (payment method is recorded as intent; proof upload
  stays mock), structured removal modifiers to KDS (removals ride in the kitchen note for now),
  real geocoding/delivery-fee calculation, and multi-branch selection (uses the primary branch).
