## 1. Backend — the `delivery.address` permission

- [x] 1.1 Add the `delivery.address` PermissionDef to `PERMISSIONS` in `identity/domain/permissions_catalog.py` (module `delivery`, described as capturing/correcting one order's delivery address — not delivery administration)
- [x] 1.2 Grant `delivery.address` in `BASE_ROLES` to `waiter`, `cashier` and `manager` (`admin` holds all codes; `courier` deliberately excluded)
- [x] 1.3 Add `require_any_permission(*codes)` beside `require_permission` in `identity/infrastructure/api/deps.py`, built on the existing `AuthorizationService.effective_codes()` (no new port method); raise the same `AuthorizationError` shape when none of the codes match

## 2. Backend — re-gate the delivery-record endpoints

- [x] 2.1 Re-gate `GET /delivery/orders/{order_id}/delivery` to accept `delivery.address` or `delivery.read`
- [x] 2.2 Re-gate `POST /delivery/deliveries` to accept `delivery.address` or `delivery.manage`
- [x] 2.3 Re-gate `PATCH /delivery/deliveries/{delivery_id}` to accept `delivery.address` or `delivery.manage`
- [x] 2.4 Confirm routes, route drivers, branch settings and run creation still require `delivery.manage` alone (no accidental widening)

## 3. Backend — tests

- [x] 3.1 Test: a user with only `delivery.address` can read, create and update an order's delivery record
- [x] 3.2 Test: a user with only `delivery.address` gets 403 on route create/edit, route drivers, branch settings and run creation
- [x] 3.3 Test: a user with only `delivery.manage` (the pre-split shape) still creates and updates delivery records — the backward-compatibility guarantee
- [x] 3.4 Test: the seeded base roles hold the expected codes (`waiter`/`cashier`/`manager` have `delivery.address`; `courier` does not) and re-seeding is idempotent
- [x] 3.5 Run `poetry run pytest`, `poetry run ruff check .` and `poetry run mypy src` green

## 4. Frontend — service and permission plumbing

- [x] 4.1 Verify `services/delivery.api.ts` needs no change (`createDelivery`, `updateDelivery`, `getOrderDelivery` already match the endpoints); add only what is missing
- [x] 4.2 Decide and document the 404 handling for `getOrderDelivery` — "sin dirección" is a state, not an error (see design §5)
- [x] 4.3 Do NOT route these calls through `stores/dispatch.ts`: its write-through `loadDeliveries()` refetches the entire delivery history (see design §3)

## 5. Frontend — capture at open (Salón)

- [x] 5.1 Add an address field to the "Nueva orden" dialog in `views/FloorView.vue`, shown only when the channel is Domicilio and the user `can('delivery.address')`
- [x] 5.2 Require the address for the dialog's own submit when shown; keep opening a delivery order possible without the permission (address left for later)
- [x] 5.3 After `openOrder` resolves, call `createDelivery({ order_id, address_text })` — no pin, letting the backend geocode
- [x] 5.4 On a failed delivery-record create: still open the ticket, surface the failure, never discard the order (see design §4)

## 6. Frontend — capture and correct on the comanda

- [x] 6.1 Build the Domicilio card component for `channel: 'delivery'` orders (leaning `components/comanda/`, beside `NoteSheet`/`PaymentSheet` — settle per design open question), owning its own local state
- [x] 6.2 Fetch `getOrderDelivery(orderId)` on mount; render 404 as the "sin dirección — agregar" invitation
- [x] 6.3 Writing from the empty state creates the record; writing over an existing one updates it
- [x] 6.4 Gate: write needs `delivery.address`; `delivery.read` alone is read-only; neither hides the card
- [x] 6.5 Mount the card in `views/OrderDetailView.vue` for delivery-channel orders only; no map picker, no pin editing
- [x] 6.6 Give the address field room to be typed into — the failure this change exists to fix was a cramped field, so follow the `NoteSheet` precedent rather than an inline input

## 7. Frontend — tests and verification

- [x] 7.1 Component test: the card shows "sin dirección" on 404, creates on first write, updates afterwards, and is read-only without `delivery.address`
- [x] 7.2 Component/unit test: the "Nueva orden" dialog requires the address for Domicilio, hides it without the permission, and keeps the order when the delivery create fails
- [x] 7.3 Test: no Domicilio card for non-delivery channels
- [x] 7.4 Run `pnpm type-check`, `pnpm lint` and `pnpm test:unit` green

## 8. End-to-end verification

- [x] 8.1 Seed the new permission (`poetry run python -m scripts.seed`) and confirm it lands on the base roles
- [x] 8.2 Drive the real flow against the running API: open a Domicilio order with an address → the delivery record exists, `pending`, and carries a **geocoded pin and neighborhood** (this is the change's whole downstream value — verify the pin, not just the row)
- [x] 8.3 Drive the comanda path: open a delivery order without an address, capture it from the card, confirm the record and pin appear
- [x] 8.4 Confirm the order now shows on the Domicilios coverage map and on the dispatch board, and that the board no longer offers that order under "Nuevo domicilio"
- [x] 8.5 Confirm a waiter-role user (only `orders.*` + `delivery.address`) can do all of the above and still cannot open `/dispatch` administration
