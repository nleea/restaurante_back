## Context

The kitchen can already turn an order's items into KDS tickets, but only when explicitly invoked
(`POST /kitchen/orders/{id}/route`, manual "Enviar a cocina"). The routing logic lives in
`KitchenService.route_order` (`kitchen/application/use_cases/manage_kitchen.py`):

- It lists the order's non-cancelled items, maps each item's variant→product, looks up the product's
  stations (`ProductStationModel`), and creates an `OrderItemStationModel` ticket per (item, station)
  — **skipping** any (item, station) that already has a ticket (`ticket_exists` guard). With no
  station mappings it creates nothing (safe no-op). It reads orders models directly.
- Dependency direction today: **kitchen → orders** (kitchen repo imports `OrderItemModel`/
  `OrderModel`). Orders imports nothing from kitchen — so there is no cycle, and we must keep it that
  way.

The orders lifecycle is `open → closed/cancelled` with no "sent/confirmed" step, so the only
incremental point where new routable items appear is `OrderService.add_item`
(`orders/application/use_cases/manage_orders.py`): it requires an open order, creates the item, and
recomputes totals.

## Goals / Non-Goals

**Goals:**
- Tickets appear automatically as items are added — no manual routing step — reusing the single
  source of routing truth (`KitchenService.route_order`).
- Keep the module layering one-way (orders must not depend on the kitchen module) and avoid a cycle.
- Be safe by construction: idempotent, a no-op without kitchen config, and non-blocking on failure.

**Non-Goals:**
- Changing/removing the manual route (kept as fallback / for pre-existing orders); auto-route on
  open/close; recall/un-route; realtime push; any frontend change.

## Decisions

**1. Hook on `add_item`.** It is the only incremental moment a new routable item exists, and the
order is already open. Auto-route on close would be wrong (close is terminal/paid — the kitchen has
long since needed the ticket); on open there are no items yet. Per-item routing matches real-time KDS
behavior and, being idempotent, re-scanning the order on each add is harmless.

**2. Reuse `KitchenService.route_order` — do not replicate.** The station-mapping→ticket logic stays
in one place. Replicating it in the orders repo (direct ticket writes) would duplicate routing rules
and drift. Orders calls the existing routing instead.

**3. Depend on an orders-owned outbound port, not the kitchen module.** Add a tiny protocol in
`orders/domain/ports.py`:
`class KitchenRouting(Protocol): async def route_order(self, tenant_id, order_id) -> None: ...`.
`OrderService` is injected with a `KitchenRouting | None` and calls it after `add_item` succeeds. The
orders application thus imports **nothing** from kitchen — the concrete adapter is wired only at the
composition root (`orders/infrastructure/api/deps.py`), where importing the kitchen service is fine.
This keeps the dependency one-way (kitchen→orders) with orders→kitchen expressed purely as an
interface, so no import cycle forms. Making the dependency optional (`| None`) means existing
construction paths and unit tests that don't supply it still work, and auto-routing is simply absent
there.

**4. Same request session.** The adapter builds the kitchen routing over the **same** `AsyncSession`
as the order service (both from the request's `get_session`), so the just-created item is visible to
routing and the tickets are written within the same request. `add_item` creates+commits the item
before routing runs, so routing's read sees it.

**5. Best-effort, non-blocking.** Routing runs inside `add_item` wrapped so that any failure is
swallowed (the item add already succeeded and is the user's intent); the manual route remains to
retry. This mirrors the "non-blocking side effect" stance of the close-time inventory deduction. The
trade-off (a swallowed error could hide a routing bug) is accepted because blocking item entry on a
kitchen hiccup is worse for the line; routing is also idempotent so a later add re-attempts it.

**6. Self-disabling without config.** Because routing yields zero tickets when there are no stations
/ product→station mappings, tenants not using the KDS get a silent no-op — no flag needed.

## Risks / Trade-offs

- **Per-add routing cost** — each add re-scans the order's items. → Bounded by order size at pilot
  volume; idempotent skips already-ticketed items.
- **Swallowed routing errors** — a genuine routing bug could go unnoticed since failures don't
  surface on add. → Accepted (non-blocking is the priority); the manual route surfaces errors, and
  tests cover the mapped/unmapped/idempotent paths.
- **Late mapping** — an item added before its product was mapped won't get a ticket until a manual
  re-route (its add-time route found no station). → Edge case; manual route covers it; noted.
- **Items added after a partial route** — each new item routes on its own add; the idempotency guard
  prevents duplicates for existing items.

## Migration Plan

Additive backend wiring (no schema change — tickets, stations, and mappings already exist) and no
frontend change. Ship the backend; the KDS board starts showing auto-created tickets. Rollback =
revert the `add_item` hook, the port, and the deps wiring; manual routing is unaffected either way.

## Open Questions

- Should auto-route be opt-out per tenant/branch (a config flag) rather than always-on? Deferred —
  it self-disables without station mappings, which covers non-KDS tenants; a flag can be added later
  if a configured tenant wants manual-only.
- Should a routing failure be recorded (e.g. an audit/log event) rather than silently swallowed? A
  reasonable hardening once a logging hook exists; out of scope here.
