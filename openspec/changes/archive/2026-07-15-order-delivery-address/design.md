## Context

`OrderDelivery` (address, neighborhood, pin, notes) is created only from `DispatchView`'s
"Nuevo domicilio" modal. The Salón's channel picker writes `order.channel = 'delivery'` and
stops there, so a delivery order is born with no delivery record at all.

Three constraints shape the design, and all three were found by reading the code rather than
assumed:

1. **The delivery module's write API is fine as-is.** `POST /delivery/deliveries` already
   geocodes when no pin is given, keeps an explicit pin, and survives a geocode failure
   (`delivery-management` → *Create a per-order delivery record*). Nothing about delivery
   behaviour needs to change — only who may call it, and from where.

2. **`delivery.manage` is one code for two unrelated jobs.** It gates the branch business pin
   and `ring_step_km`, route create/edit (the delivery rings), the route driver roster, run
   creation — *and* the per-order address. Granting it to whoever answers the phone hands
   them the delivery geography of the business.

3. **The order-taking roles hold no delivery permission whatsoever:**

   ```
   waiter   : menu.read, orders.read, orders.create, orders.update, customers.read
   cashier  : menu.read, orders.{read,create,update,pay}, cash.*, customers.*
   ```

   Neither has `delivery.read`, so today they cannot even *read* an order's delivery
   (`GET /delivery/orders/{order_id}/delivery` is gated `delivery.read`).

## Goals / Non-Goals

**Goals:**

- Capture the address at the moment it is heard: in the "Nueva orden" dialog, and on the
  comanda for the life of the open order.
- Let waiters and cashiers do it without handing them delivery administration.
- Keep `/dispatch` working exactly as it does today, as the fallback path.
- Preserve the existing geocode-on-create behaviour untouched, so a captured address yields
  a pin for free.

**Non-Goals:**

- Blocking close/settle on a missing address.
- A map picker, pin editing, or paste-a-location on the order screens. Text address only;
  `/dispatch` keeps those.
- Branch scoping of `order_deliveries` (tenant-scoped today, against the project's binding
  rule) — separate change.
- Touching the dispatch board's own list/filter behaviour.

## Decisions

### 1. A new `delivery.address` permission, not a broader grant

`delivery.manage` stays with routes, route drivers, branch settings and run creation.
`delivery.address` covers exactly one concept: **read and write one order's delivery
record**.

Granted to `waiter`, `cashier`, `manager`, `admin`. Not to `courier` (a driver reads the
board, does not author addresses).

Alternatives considered:

- *Grant `delivery.manage` to waiter/cashier* — rejected: a waiter could move the business
  pin and redraw the rings.
- *Re-gate `POST /deliveries` to `orders.update`* — rejected: gating one module's endpoint on
  another module's permission inverts the RBAC model, and `orders.update` is held by roles
  that should not necessarily author addresses.
- *A new `POST /orders/{id}/delivery-address` in the orders module, mirroring the fiado
  `POST /orders/{id}/customer`* — rejected: the precedent does not hold. `assign_customer`
  sets `order.customer_id`, a column on the orders module's own table. The address lives in
  `order_deliveries`, owned by the delivery module; routing it through orders would make the
  orders module write another module's table and break the `API → application → domain`
  layering the project keeps.

### 2. `require_any_permission(*codes)` for backward compatibility

`require_permission` enforces a single code, so re-gating endpoints from `delivery.manage`
to `delivery.address` would **403 any custom tenant role that holds only `delivery.manage`**
— a silent regression for installs whose roles were edited through `/rbac`.

Three endpoints therefore accept either code:

| Endpoint | Accepts |
|---|---|
| `GET /delivery/orders/{order_id}/delivery` | `delivery.address` or `delivery.read` |
| `POST /delivery/deliveries` | `delivery.address` or `delivery.manage` |
| `PATCH /delivery/deliveries/{delivery_id}` | `delivery.address` or `delivery.manage` |

`AuthorizationService.effective_codes()` already returns the full effective set, so the
helper is a thin sibling of `require_permission` with no new port method and no resolver
change.

The `GET` pairing is what makes the comanda card readable: `delivery.read` is the gate for
the whole Domicilios surface (the board, routes, settings) and the frontend nav gates on it,
so granting it to a waiter would put `/dispatch` in their menu. `delivery.address` gives them
one order's record and nothing else.

### 3. The order screens call `services/delivery.api.ts` directly — never `stores/dispatch.ts`

`useDispatchStore` is write-through against the *whole* board: every mutation ends in
`loadDeliveries()`, which is `GET /delivery/deliveries` with no date filter, no pagination —
every delivery the tenant has ever had. That is defensible for the board; calling it from the
comanda to save one address would download the entire delivery history per keystroke-save.

So:

- **FloorView** calls `createDelivery(...)` from the API module directly — a one-shot call
  after `openOrder` resolves.
- **The comanda card** owns its own local state, fetching `getOrderDelivery(orderId)` on
  mount and calling `createDelivery` / `updateDelivery` itself.

Neither surface loads the board's collections. This also keeps the address feature immune to
the dispatch store's refetch behaviour, which is known debt tracked elsewhere.

### 4. Open-then-create, deliberately non-atomic

`openOrder` then `createDelivery` are two calls. A failure of the second leaves
`channel: 'delivery'` with no address — **exactly today's baseline**, and the comanda card
resolves it. Capturing in both places is what makes the non-atomic path safe, so no backend
transaction, saga, or composite endpoint is introduced.

The dialog therefore treats the address as required for its own submit, while the *system*
tolerates its absence.

### 5. `GET /orders/{id}/delivery` 404 is a state, not an error

A `channel: 'delivery'` order with no delivery record is the normal starting point for every
order opened before this change, and for any order whose create call failed. The card reads
404 as "sin dirección — agregar", not as a failure to report.

## Risks / Trade-offs

- **A custom role holding only `delivery.manage` keeps working, but a custom role built to
  mimic `waiter` will not gain `delivery.address` automatically.** → `seed_rbac` is additive
  over `BASE_ROLES` (the global base roles), so tenant-custom roles are untouched by design.
  Release note: grant `delivery.address` to any custom order-taking role via `/rbac`.

- **A seeded permission is invisible to logged-in users until the cache expires.** The API
  wires `AuthorizationService(resolver=CachedPermissionResolver(...))` — a read-through cache
  keyed `rbac:perms:{tenant}:{user}` with `settings.cache_ttl_seconds` (300s). `RbacService`
  invalidates on grants made through `/rbac`, but the **seed writes straight to the DB and
  never invalidates**. → In practice benign: the deploy restarts the process, and
  `CACHE_BACKEND=memory` starts empty. With `CACHE_BACKEND=redis` the stale window is one TTL
  (5 min). Seed *before* announcing, or accept a 5-minute rollout.

- **Address quality drops.** A dispatcher typing from a note may normalise; a waiter typing
  live will not. Geocoding is best-effort and biased to the branch, so a vague address yields
  a wrong-but-plausible pin rather than none. → The pin stays correctable from `/dispatch`,
  which keeps the picker. Not solved here.

- **Two creation paths for one record.** The board's "Nuevo domicilio" and the order screens
  can both create. The 409 on a second delivery for the same order already guards this, and
  the board already excludes orders that have one. → Keep both; the board's path becomes the
  fallback rather than the primary.

- **Scope pressure toward the map picker.** Once the address lives on the comanda, "let me
  just drop the pin here too" is one request away. → Held out deliberately: the geocoder
  places the pin, and `/dispatch` corrects it.

## Migration Plan

1. Add `delivery.address` to `PERMISSIONS` and to `BASE_ROLES` (waiter, cashier, manager).
2. Add `require_any_permission`; re-gate the three endpoints.
3. Deploy backend, then run `poetry run python -m scripts.seed` — idempotent and additive, it
   inserts the permission and grants it to the base roles. **No Alembic migration**:
   permissions are rows, not schema.
4. Deploy frontend. On a Redis-backed install, allow one `cache_ttl_seconds` window (5 min)
   for logged-in users to pick the permission up; a memory-backed install is clear on restart.

**Rollback:** revert the router gating (endpoints return to `delivery.manage` / `delivery.read`)
and the frontend. The orphan `delivery.address` rows are inert — an ungated permission code
grants nothing.

**Ordering:** the backend must ship first, or the new screens 403 for waiters and cashiers.

## Open Questions

- Should `courier` receive `delivery.address`? Excluded here on the reasoning that a driver
  consumes addresses rather than authors them — but a driver correcting a bad address at the
  door is a plausible real flow, and it is a one-line change if wanted.
- Does the comanda's Domicilio card belong in `components/comanda/` next to `NoteSheet` and
  `PaymentSheet`, or is a delivery-owned component imported into the comanda the better seam?
  Leaning `components/comanda/` — the card is an order-screen concern that happens to call the
  delivery API. Settled at implementation.
