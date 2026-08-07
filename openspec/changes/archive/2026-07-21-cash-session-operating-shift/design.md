## Context

Deliveries list only by `tenant_id + branch_id` (no time/session bound), so the dispatch board shows every delivery ever created. Orders have `created_at` and `status` but **no** `cash_session_id`; the only order↔session link is `order_payments.cash_session_id`, written at payment time. Cash sessions are branch-scoped with `status` open/closed and one open session per branch (`CashRepository.get_open_session(tenant, branch)`).

Decisive finding: **all order creation funnels through `OrderService.open_order`** (`manage_orders.py:178`). Salón/comanda and the storefront (`manage_storefront.create_order` → `self._orders.open_order`) both go through it. So the gate and the `cash_session_id` stamp live in exactly one place and cover every channel.

## Goals / Non-Goals

**Goals:**
- Make the open cash session the operating-shift boundary for live operational boards.
- Stamp every new order with the branch's open session; reject creation when none is open.
- Deliveries/kitchen/salón live views show only the current open session's work; closed/old work drops off.

**Non-Goals:**
- Structured opening hours and the "abrimos a las X" copy (later change) — the rejection is a generic "caja cerrada" for now.
- Close-caja pending summary / force-close behavior (later change).
- Per-closed-session history/report screens (later change).
- Backfilling `cash_session_id` on existing rows.

## Decisions

**1. Anchor the session on the ORDER; deliveries/kitchen inherit via join.**
Only `orders` gets `cash_session_id`. Deliveries and kitchen tickets resolve the session through their order, so there is a single source of truth and no multi-row drift.
*Alternative considered:* stamp each delivery/ticket independently. Rejected — three columns to keep consistent, and the order is the operational core they already hang off.

**2. Gate + stamp in `OrderService.open_order` (the one choke point).**
`open_order` calls `get_open_session(tenant, branch)`. If `None` → raise `CashClosedError`; else set `order.cash_session_id = session.id`. Covers salón, storefront, and delivery-origin creation in one edit.
*Alternative considered:* gate per channel (router-level). Rejected — duplicated logic, easy to miss a channel, and the storefront already delegates to `open_order`.

**3. New `CashClosedError` → HTTP 409, mapped centrally.**
A distinct domain error (not a generic `ValidationError`) so every frontend can detect "caja cerrada" and render the closed state, distinct from a 422 validation failure. Mapped in `shared/api/errors`.
*Alternative considered:* reuse `ConflictError`. Rejected — callers couldn't distinguish "closed" from other 409s to drive the specific UX.

**4. Live boards filter by the branch's open session; null excluded.**
Delivery/kitchen/salón list queries resolve the branch's open session and filter orders (or their deliveries/tickets) to `cash_session_id = <open session>`. When no session is open, the live list is empty (and the UI shows the closed state). Rows with `cash_session_id = null` (pre-change data) never match, so they drop off with no backfill.
*Alternative considered:* filter by `created_at >= opened_at` time window. Rejected — fragile at boundaries (reopen, clock skew, born-just-before-open); the explicit stamp is unambiguous and gives free per-session history later.

**5. New cross-module edge `orders → cash` at creation.**
`open_order` needs the open-session resolver. Inject the cash repository/port into `OrderService` (the payment path already couples the two modules, so this follows precedent).

## Risks / Trade-offs

- **No open caja blocks ALL new orders, including public storefront** → intended (that's "the restaurant is open when the caja is open"). Mitigation: the rejection is explicit and, in a later change, enriched with opening hours so the customer sees when it reopens.
- **Salón dine-in gated too** → confirmed desired ("despacho, salón, todo"). A caja must be opened before service starts.
- **Existing (test) data disappears from live boards** → desired outcome (decision C); it remains in the DB, queryable, just not "live".
- **Delivery still in the street when its session logic is evaluated** → deliveries stay tied to their order's session regardless of delivery_status, so an in-progress delivery keeps showing while its session is open; closing the caja with one still out is handled by the *close-caja* change (warn + force-close), not here.

## Migration Plan

1. Add `orders.cash_session_id` (nullable FK, indexed) — Alembic migration; register nothing new (column on existing table).
2. Wire the cash open-session resolver into `OrderService`; add gate + stamp in `open_order`; add `CashClosedError` + error mapping.
3. Scope delivery/kitchen/salón list queries to the open session.
4. Frontend: dispatch consumes the scoped list + closed state; storefront/salón surface the rejection.
5. Rollback: drop the column and revert `open_order`; no data migration to undo.

## Open Questions

- Should the salón (dine-in) creation gate and the delivery gate share the exact same `CashClosedError`, or does salón need a softer path (e.g., staff can still open a table but not fire)? Default: same hard gate at `open_order`.
- Does the kitchen board also need to keep showing tickets whose order was created in a now-closed session but are still cooking at cutover? Default: no — closing the caja is an explicit shift end; in-flight tickets are handled by the close-caja change.
