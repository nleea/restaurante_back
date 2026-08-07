## Why

The backend `/kitchen` module (stations, product→station routing, and a `pending → in_progress →
ready` ticket board) has no frontend, so the cocina has no Kitchen Display System (KDS) — cooks
can't see what to prepare and the order→kitchen leg of the operational loop is unusable from the
UI. Nothing creates tickets today either: seed sets up no stations or mappings, and closing an
order does not auto-route, so the screen must also let an operator configure stations, map
products to them, and route open orders. This is the next operational screen after orders/cobro.

## What Changes

- Add a **Kitchen service layer** (`kitchen.api.ts`) over `/kitchen`: stations
  (`list/create/update`), product↔station mappings (`list/attach/detach`), order routing
  (`POST /orders/{id}/route`), ticket listing per station (`GET /stations/{id}/tickets`), and
  ticket advance (`POST /tickets/{id}/advance`).
- Add a **Kitchen store** (`kitchen.ts`): stations, per-station tickets, product→station
  mappings, and a client-side resolver that labels a ticket (by `order_item_id`) with its
  product/variant name and quantity using the existing menu/orders data, degrading gracefully
  when an item can't be resolved.
- Add the **KitchenView** screen with three areas, mobile-first per the house master–detail
  pattern:
  - **Board** (cook-facing): pick a station → tickets shown in `pending / in_progress / ready`
    columns; advancing a ticket moves it forward. Read needs `kitchen.read`; advancing needs
    `kitchen.update`.
  - **Setup**: station CRUD (name, position, active) and product→station mapping, gated by
    `kitchen.update`.
  - **Routing**: list open orders not yet routed and offer "Enviar a cocina"
    (`POST /kitchen/orders/{id}/route`), so tickets appear on the board.
- Add the **route + nav entry** (`/kitchen`, permission `kitchen.read`) and a navigation link.
- Unit tests for the service and store (including ticket-label resolution and the advance/route
  write-through).

Non-goals: bump-bar/auto-refresh or realtime push (manual refresh for this slice), per-item
timing/SLA metrics, recall/un-advance of a ready ticket, station load balancing, and printing.

## Capabilities

### New Capabilities
- `frontend-kitchen`: the KDS frontend — station setup, product→station mapping, routing open
  orders to the kitchen, and the cook-facing ticket board with forward-only advancement, all
  scoped to the active branch and gated by `kitchen.read` / `kitchen.update`.

### Modified Capabilities
<!-- None. Routing is triggered from the KDS screen, so the frontend-orders capability is
     untouched. -->

## Impact

- **Frontend code**: new `front/src/services/kitchen.api.ts`, `front/src/stores/kitchen.ts`,
  `front/src/views/KitchenView.vue`, and `front/src/components/kitchen/*`; a route in
  `front/src/router/index.ts` and a nav link. New tests under `front/src/services/__tests__`
  and `front/src/stores/__tests__`.
- **Reuses**: the menu store (product list for mapping + label resolution), the orders API
  (open orders for routing; order items for ticket labels), the `apiError` helpers, COP/label
  utilities, and the active-branch context.
- **Backend**: none — consumes existing `/kitchen` endpoints (`kitchen.read` / `kitchen.update`).
- **Permissions/RBAC**: relies on `kitchen.read` (screen + board) and `kitchen.update` (setup,
  routing, advance); no new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
