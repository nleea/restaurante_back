## 1. Backend · public storefront router (reads)

- [x] 1.1 Create a public `storefront` router (tenant via `TenantDep`, NO `require_permission`),
  mounted in `main.py` under `/storefront`.
- [x] 1.2 `GET /storefront/appearance`: reuse the appearance use case to return the saved config or
  default; no auth. Add a schema response mirroring the appearance config.
- [x] 1.3 Build the menu read-model assembler: active categories; per active product → name,
  description, image_url, primary-branch price, sellable variant id, addons (id/name/price), and
  recipe-derived removable ingredient names filtered by `is_customer_removable`. Customer-safe only.
- [x] 1.4 `GET /storefront/menu`: return the read-model; resolve the primary branch for prices.
- [x] 1.5 Tests: appearance default + saved (no auth); menu excludes inactive items, filters
  removables by the flag, and leaks no cost/quantity fields.

## 2. Backend · order intake

- [x] 2.0 Migration `0017_order_payment_method`: add nullable `orders.payment_method` (String(30));
  thread it through the order model/entity/repository/OrderResponse schema (optional, default null).
- [x] 2.1 System-employee resolver: get-or-create a per-tenant "Pedidos web" employee.
- [x] 2.2 Customer find-or-create-by-phone helper (reuse the customers use cases); require name+phone.
- [x] 2.3 `POST /storefront/orders` request schema: contact (name, phone required), fulfillment
  (`pickup|delivery` + address/GPS), payment method choice, and lines (variant id, quantity,
  addon ids, removed ingredient names, note).
- [x] 2.4 Compose transactionally: customer → open order (channel `takeaway`/`delivery`, system
  employee, `payment_method` intent) → per line add item + attach addons + set note (removals folded
  in) → delivery attach when delivery. Leave the order open/unpaid and PENDING (do NOT fire to the
  kitchen). Return order id/number + status.
- [x] 2.5 Tests: pickup order created with items+addons; delivery order attaches delivery; removals
  present in the item note; payment_method recorded (no order_payments row); same phone reuses the
  customer; empty/invalid cart → 422; order lands open/unpaid and pending (items not auto-fired).

## 3. Frontend · storefront API + data wiring

- [x] 3.1 `services/storefront.api.ts`: `getAppearance()`, `getMenu()`, `createOrder(payload)`
  typed to the storefront types.
- [x] 3.2 Map the public menu response into `StorefrontProduct`/`Addon`/`StorefrontCategory`
  (`lib/storefront.ts`); include the sellable variant id needed for ordering.
- [x] 3.3 `StorefrontView`: replace `mockPublishedConfig` with fetched appearance (theme vars +
  ordered blocks); add loading/empty/error states; keep the default-fallback so the page never
  blanks.
- [x] 3.4 `StorefrontView`: replace `mockCategories`/`mockProducts` with the fetched menu; search +
  category nav operate over real data; product detail shows real addons + removables.

## 4. Frontend · real checkout

- [x] 4.1 Assemble the order payload from `stores/cart` (lines with variant id, qty, addons, removed
  ingredients, note; fulfillment + address/GPS; contact) and POST via `createOrder`.
- [x] 4.2 `ConfirmationStep`: show the server-returned order number + status; surface submission
  errors without clearing the cart.
- [x] 4.3 Remove the mock carta from the live path (keep types); delete/retire `mock/storefront.ts`
  usage in `StorefrontView`.

## 5. Verify

- [x] 5.1 Backend: `poetry run pytest` for storefront/menu/orders green; endpoints behave per spec
  (no-auth reads, order intake, flag-filtered removables).
- [x] 5.2 Frontend: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build` clean.
- [ ] 5.3 Manual E2E at `demo.localhost:5173/store`: page wears the saved theme; real dishes list;
  detail shows real addons + removables (staples absent); place a pickup + a delivery order →
  confirmation shows a real number → order appears in the kitchen/dispatch boards.
