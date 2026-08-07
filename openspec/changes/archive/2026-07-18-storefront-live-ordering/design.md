## Context

`/store` (`StorefrontView.vue` + `components/storefront/*` + `stores/cart.ts`) is a complete, mock
customer flow: it reads `mockPublishedConfig` (appearance) and `mockCategories`/`mockProducts`
(`mock/storefront.ts`), themes itself via `--sf-*` CSS vars, and the checkout confirms nothing. The
route is already public (`meta.public`, no AppShell). Fase 2 persisted the appearance config
(`GET /menu/appearance`, `menu.read`-gated) and added the `is_customer_removable` ingredient flag.

The backend resolves the tenant from the subdomain via middleware; `/auth/login` proves an endpoint
can be tenant-scoped WITHOUT auth (uses `TenantDep`, no `require_permission`). Orders use
`channel ∈ {dine_in, takeaway, delivery}`, `orders.employee_id` is NOT NULL (RESTRICT), delivery is
a separate module (`CreateDeliveryRequest{address_text, latitude?, longitude?}`), and customers
have create-by-phone. Order items carry a free-text `notes`; structured KDS modifiers were deferred.

## Goals / Non-Goals

**Goals:**
- Public, no-auth, subdomain-scoped endpoints: appearance, menu read-model, order intake.
- `/store` renders the real menu themed by the saved config, with real addons + flag-filtered
  removables in the product detail.
- Checkout creates a real, open/unpaid order that reaches the kitchen/dispatch flow.

**Non-Goals:**
- No new tables (system employee reuses `employees`); the only schema change is one nullable
  `orders.payment_method` column.
- No real payment capture / gateway; payment method is recorded as intent, proof stays mock.
- No structured removal modifiers to KDS (removals fold into the item note this phase).
- No real geocoding / delivery-fee math; no multi-branch (primary branch only).
- No abuse controls (rate limit / captcha) — acknowledged, deferred.

## Decisions

### A dedicated public `storefront` router, no auth, tenant by subdomain
Rather than making the `menu.read`-gated endpoints public, add a separate `storefront` router whose
endpoints depend only on `TenantDep` (the `/auth/login` pattern). This keeps the authed admin API
gated and gives the public surface its own, deliberately minimal read-model — the only place we
expose customer-safe data. Alternative (add `public=true` variants under `/menu`) — rejected:
muddies the gated module and risks leaking internal fields.

### The menu read-model is assembled server-side, customer-safe
`GET /storefront/menu` composes menu (categories/products/prices/addons), the sellable variant id
per product, and recipe-derived removable ingredient NAMES (filtered by `is_customer_removable`).
It emits only public fields — never cost, never BOM quantities. Assembling server-side keeps the
client a dumb renderer and avoids N public round-trips.

### Order creation composes existing use cases on a system employee
`POST /storefront/orders` runs the same sequence staff do, server-side in one transaction:
find-or-create customer by phone → open order (channel `takeaway`|`delivery`, `employee_id` = the
tenant's system employee) → per line: add item (by sellable variant), attach addons, set the kitchen
note → if delivery, create+attach a delivery. The order is left `open`/unpaid (staff confirm/close
later — consistent with "close requires payment"). Reusing the vetted use cases means inventory
deduction, KDS auto-fire, and dispatch all behave exactly as for staff orders.

### System employee resolved-or-created per tenant
`orders.employee_id` is NOT NULL; a public customer has no employee. A per-tenant "Pedidos web"
employee is resolved (or lazily created) and used for web orders. This avoids making the column
nullable (which would ripple through order queries and reporting). Alternative (nullable employee /
new channel) — rejected as higher blast radius for one attribution need.

### Payment method is an order intent, not an `order_payments` row
`order_payments` models money actually received (it requires a `cash_session_id` and an amount, and
has no `pending` state) — so it cannot represent an unpaid web order's chosen method. Instead a
nullable `orders.payment_method` column records the customer's choice as an intent; staff register a
real `order_payments` row when they collect. This keeps paid-total/close semantics untouched.
Alternative (fake pending payment row) — rejected: it would corrupt cash/close math.

### Storefront orders land pending — no auto-fire
`add_item` creates items *pending*; staff compose and fire via `set_kitchen_state`. A web order
follows the same path: it lands pending and visible to staff, who confirm and fire it — so a bogus
or mistaken remote order is never cooked before validation. A delivery order still enters Dispatch
as pending (the existing delivery side effect). Auto-firing — rejected as unsafe for unreviewed
public input.

### Removals ride in the kitchen note (structured modifiers deferred)
Excluded ingredients are folded into the order item's `notes` (e.g. "Sin cebolla · <nota>"), which
KDS already renders prominently. Structured `modifiers` remain a later change; this delivers kitchen
visibility now without new order-item structure.

### Frontend: swap the data source, keep the flow
`services/storefront.api.ts` adds `getAppearance`/`getMenu`/`createOrder`. `StorefrontView` replaces
the mock constants with fetched data (config → theme vars; menu → `StorefrontProduct[]`), adding
loading/empty/error states. The mapping targets the existing `StorefrontProduct`/`Addon` types, so
`stores/cart` and the checkout components barely change; `ConfirmationStep` shows the server order
number. `crypto.randomUUID()` line uids and thermal-ticket UI are unchanged.

## Risks / Trade-offs

- **Public write endpoint = abuse surface** → spam/garbage orders. Mitigation: order is open/unpaid
  and staff-gated before it closes; note rate-limiting as a fast follow. Do not expose it beyond
  what the storefront needs.
- **Variant selection**: `add_item` needs a sellable variant; a product may have several. Mitigation:
  the read-model exposes one sellable variant id per product (the product's default/only active
  variant); multi-variant customer choice is a later refinement.
- **Price/branch ambiguity**: prices are per-branch. Mitigation: use the tenant's primary branch;
  document it; a branch selector is out of scope.
- **Read-model drift from `StorefrontProduct`** → Mitigation: shape the endpoint to the existing
  frontend type (description/price/imageUrl/removableIngredients/addonIds) so mapping is near-1:1.
- **Partial failure mid-compose** (e.g. delivery attach fails after order opens) → Mitigation: run
  the composition transactionally so a failed order intake leaves nothing half-created.

## Migration Plan

Additive: new public endpoints + a system-employee resolver; no tables, no schema changes, no data
migration. The demo seed MAY create the system employee up front, but lazy creation makes it
optional. Rollback = revert; nothing persisted beyond orders customers legitimately placed.

## Open Questions

- Should the confirmation surface a way for the customer to track status later (order number only vs
  a public status lookup)? (Leaning: order number + static status this phase; public tracking later.), public traking later
- Payment method intent: store it as an order note / metadata, or a pending `payments` row with
  state `pending`? (Leaning: note/metadata now; a pending payment row when payment goes real.) payments 
- Should placing an order require a minimum contact (name + phone) always, or allow pickup with just
  a name? (Leaning: require phone so customer reuse + kitchen callback work.), name - contact
