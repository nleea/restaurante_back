# Capture the delivery address where it is heard: at open and on the comanda

## Why

Choosing "Domicilio" in the Salón today sets **only a channel string** on the order. No
`OrderDelivery` record is created, so there is no address, no pin, and nothing for the
Domicilios map or the dispatch board to show. The address can only be typed later, from
`/dispatch` → "Nuevo domicilio", by a *different person on a different screen* — who was
never on the phone and is working from a note or from memory.

Meanwhile the person taking the order has the address in their ear at that exact moment.
The system forces it to be forgotten and re-entered. That is the whole gap.

Two things make this the right moment:

- **The plumbing already exists.** `POST /delivery/deliveries` takes `{order_id,
  address_text, …}` and `PATCH /delivery/deliveries/{id}` edits it. No new delivery
  behaviour is needed — only a caller and the right permission.
- **Geocoding started working today** (the Nominatim User-Agent carried a placeholder
  contact and was answering 403 in silence). An address captured here now yields a pin and
  a neighborhood automatically, biased to the branch. Every downstream idea — ring
  inference, the coverage map, "sin ubicación" counts — depends on deliveries having pins,
  and today **not one real delivery has one**.

## What Changes

The order-taking surfaces gain the address; the delivery module keeps owning it.

- **The Salón's "Nueva orden" dialog** asks for the address when the channel is Domicilio,
  and creates the delivery record right after opening the order.
- **The comanda (`/floor/order/:id`)** shows a Domicilio card for `channel: 'delivery'`
  orders: it captures the address when the order has none, and edits it afterwards. This is
  the same shape as the kitchen note and the fiado customer picker — capture where there is
  room, correct later.
- **BREAKING (RBAC): a new `delivery.address` permission** splits "write a delivery's
  address" out of "administer delivery operations". Today `delivery.manage` gates the
  business pin, the delivery rings, the driver roster, runs **and** the address, all as one
  code — so letting a waiter type an address would also let them redraw the delivery rings
  and move the business location. `delivery.manage` keeps routes / drivers / settings /
  runs; `delivery.address` gates creating and updating a delivery record.
  - Granted to `waiter`, `cashier`, `manager`, `admin` (whoever answers the phone).
  - `courier` does not get it.
  - Existing installs pick it up by re-running the seed (permissions are additive data,
    not schema — no Alembic migration).

Explicitly **out of scope**:

- **No close/settle gate.** A delivery order with no address can still be charged and
  closed. Considered and rejected for now.
- **No map picker on the order screens.** The pin comes from the geocoder; the manual
  picker and paste-a-location flow stay in `/dispatch`, which already has them. Text
  address only here.
- **No branch scoping fix.** `order_deliveries` is tenant-scoped rather than branch-scoped
  (against the project's binding rule) — that is its own change.

## Capabilities

### New Capabilities

None. This wires existing delivery behaviour to new callers and re-cuts one permission.

### Modified Capabilities

- `delivery-management`: **RBAC protection of delivery endpoints** — delivery-record
  create/update move from `delivery.manage` to the new `delivery.address`; `delivery.manage`
  narrows to routes, route drivers, branch settings and run creation.
- `frontend-salon`: **Create a delivery order from the Salón** — the dialog now captures a
  required address for the Domicilio channel and creates the delivery record; plus a new
  requirement for the comanda's Domicilio card (view and edit the address on an open order).
- `frontend-delivery-dispatch`: **Manage deliveries** — the board's create/update-delivery
  flows are gated by `delivery.address` instead of `delivery.manage`; the board stays the
  fallback for orders that arrived without one.

## Impact

**Backend**

- `identity/domain/permissions_catalog.py` — new `delivery.address` PermissionDef; added to
  `BASE_ROLES` for waiter / cashier / manager (admin holds all).
- `delivery/infrastructure/api/router.py` — re-gate `POST /deliveries` and
  `PATCH /deliveries/{id}`.
- Backward compatibility: `require_permission` takes a single code, so a custom tenant role
  holding only `delivery.manage` would lose delivery-record access. Needs an any-of check or
  an explicit decision — resolved in `design.md`.
- No Alembic migration. `scripts/seed.py` (`seed_rbac`) is idempotent and additive.

**Frontend**

- `views/FloorView.vue` — address field in the "Nueva orden" dialog; open-then-create-delivery.
- `views/OrderDetailView.vue` + `components/comanda/` — the Domicilio card.
- `stores/dispatch.ts`, `services/delivery.api.ts` — reused as-is (`createDelivery`,
  `updateDelivery`, `getOrderDelivery`).
- `stores/auth.ts` `can()` gating on the new code.

**Failure mode (deliberate)**

Opening the order and creating the delivery are two calls. If the second fails, the order
exists as `channel: 'delivery'` with no address — which is exactly today's baseline, and the
comanda card can fix it. Capturing in *both* places is what makes the non-atomic path safe,
so no backend transaction is needed.
