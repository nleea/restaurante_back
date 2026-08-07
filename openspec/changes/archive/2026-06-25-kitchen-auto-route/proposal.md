## Why

The kitchen backend can route an order's items into KDS tickets, but nothing fires it
automatically — a waiter must open the Cocina screen and click "Enviar a cocina" for every order.
That manual step is easy to forget and delays the line. Since tickets should appear as the order is
taken, the natural fix is to route automatically when an item is added to an order, so the cocina
sees dishes the moment they're entered — no extra step.

## What Changes

- **Backend**: when an item is added to an open order, the system also routes that order to the
  kitchen — creating a ticket for each routable item (its product mapped to a station) — reusing the
  existing kitchen routing logic. The route is **idempotent** (an item already ticketed at a station
  is skipped) and a **safe no-op** when the kitchen isn't configured (no stations / product→station
  mappings → zero tickets), so non-KDS tenants are unaffected. It is **best-effort and non-blocking**:
  if routing fails, the item is still added and the manual "Enviar a cocina" remains as a retry.
  - `orders/domain/ports.py`: a small outbound port `KitchenRouting` (`route_order(tenant_id,
    order_id)`), so the orders application depends on an interface — not the kitchen module — keeping
    the layering one-way (kitchen already imports orders models; orders must not import kitchen).
  - `orders/application/use_cases/manage_orders.py`: `add_item` calls the injected `KitchenRouting`
    after the item is created (guarded, non-blocking).
  - `orders/infrastructure/api/deps.py`: wire an adapter that delegates to the kitchen routing
    service over the **same request session**, so the just-added item is visible and tickets are
    created in the same request.
- Tests: adding an item whose product is mapped to a station creates a ticket on that station; an
  unmapped product creates none (and the add still succeeds); routing is idempotent; existing manual
  routing and kitchen tests stay green.

Non-goals: changing the manual "Enviar a cocina" routing (kept as a re-route / fallback and for
orders predating this change); auto-routing on order open or close (item-add is the only point where
new routable items appear); recall/un-route; realtime push to the board (manual refresh, as today);
and any frontend change — the KDS board already shows tickets, so they simply appear without the
manual click.

## Capabilities

### Modified Capabilities
- `order-management`: adding an item to an order SHALL also route the order to the kitchen
  (best-effort, idempotent, a no-op when no station mappings exist) — a new item-add side effect, so
  KDS tickets are created automatically instead of via a manual step.
- `kitchen-management`: the Purpose note listing "automatic routing on item add" as out of scope is
  retired — it is now performed by the order item-add flow (a prose correction; the kitchen routing
  logic and the manual route endpoint are unchanged).

## Impact

- **Backend code**: `orders/domain/ports.py` (new `KitchenRouting` port),
  `orders/application/use_cases/manage_orders.py` (`add_item` hook + constructor dependency),
  `orders/infrastructure/api/deps.py` (adapter wiring over the shared session); plus
  `tests/modules/orders/...` (assert a ticket appears on item add).
- **Frontend code**: none — the kitchen board already renders tickets; the manual Ruteo area remains
  as a fallback.
- **Backend behavior change (intentional)**: adding an order item now also creates kitchen tickets
  for mapped products, in the same request. No behavior change when the kitchen isn't configured.
- **Permissions/RBAC**: unchanged — auto-routing is an internal call inside the `orders.write`-gated
  item-add; no separate `kitchen.update` is required for the automatic path.
- **Dependencies**: none.
