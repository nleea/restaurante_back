## Context

The driver view (`/driver`) is built but mock-backed (`lib/driver/mockDriver.ts`, in-memory `useDriverStore`). The real delivery backend (`modules/delivery`) models runs and deliveries but exposes only dispatcher-oriented endpoints: run creation needs `delivery.manage`; assign/depart/finish/mark-delivered need `delivery.assign`; list endpoints filter by `branch_id`+`status` only, never by driver. Identity is available (`GET /staff/employees/me` maps the auth user to an `Employee`; `delivery_runs.employee_id` is the driver linkage). Order-level detail the driver needs at the doorstep (customer, phone, items, total, payment) lives in `modules/orders`, joined by `order_id` — not on the delivery.

Product constraint from the user: **not every business has a dispatcher.** A driver must be able to open and work a despacho on their own, while the dispatcher path keeps working for businesses that do have one.

## Goals / Non-Goals

**Goals:**
- A driver, holding only `delivery.drive`, can self-open a run, read *their own* run with order-enriched stops, depart/finish it, and mark stops delivered / not-delivered (with a reason) — all authorized by run ownership, never by dispatcher permissions.
- The dispatcher's existing create+assign+lifecycle path is unchanged and interoperable (a dispatcher-created run is workable by its driver; a driver-opened run is visible to the dispatcher).
- The driver app never needs branch-wide `orders.read`.
- Wire the frontend to real data; delete the mock layer (except the geolocation constant, owned by Change 2).

**Non-Goals:**
- Browser geolocation, storing the driver's position trail, and the driver marker on the dispatcher map — all in Change 2 (`driver-live-location`).
- Redesigning the dispatcher board or the run-assignment UX.
- Editing order contents from the driver app (drivers never mutate items/prices).

## Decisions

### D1 — Dual-path run opening; the driver self-opens by pulling eligible deliveries
A driver-facing action creates a run owned by the caller (`employee_id = me`, status `preparing`) and **pulls** the branch's eligible pending deliveries into it, then leaves it ready to depart. "Eligible" = same branch as the driver, `delivery_status == pending`, `delivery_run_id is null` — **zone-agnostic** (per the user: "no importa la zona"; opening a despacho grabs the branch's pending drops regardless of route zone). The run still needs a route as its vehicle (FK): the driver must be an active driver of ≥1 route; with exactly one, it is used; with several, the driver passes the chosen `delivery_route_id`; with none, the open is rejected with a clear "no route assigned" error (a one-time admin setup, not per-despacho dispatcher work). **One active run at a time**: the driver must finish (all delivered/not-delivered → back at the restaurant → "disponible") before opening another; opening while one is active returns the existing run. A driver MAY unassign a wrongly-pulled delivery back to the pool while the run is still `preparing`.
- *Why:* mirrors the real small-shop operation ("someone hands the driver the pending orders, or nobody does"). Reuses the existing `assign` transition (pending→assigned onto a preparing run) rather than inventing a second assignment mechanism; the pull is zone-agnostic because small shops don't partition drops by ring.
- *Alternatives:* (a) driver picks individual deliveries — more control, more taps; keep as a later refinement. (b) assign deliveries directly to an employee without a run — rejected: the run *is* the batch, and a second assignment model would fork the lifecycle. (c) route-scoped pull — rejected per the user's "zone doesn't matter".

### D2 — A dedicated driver read model with order enrichment
Add `GET /delivery/me/run` returning the caller's active run (`preparing` or `in_transit`) with its deliveries ordered by `route_position`, each **enriched** with an order summary read from `modules/orders`: order code, customer name + phone, item lines (name + qty), total, payment method, and paid/unpaid state. Returns empty/`null` when the driver has no active run.
- *Why:* keeps the driver app on a single, least-privilege endpoint; avoids shipping the whole branch's deliveries or granting `orders.read`.
- *Trade-off:* introduces a read-only dependency from delivery → orders. Mitigate by a query/DTO at the application layer (no write coupling, no new FK).

### D3 — Authorization by ownership under `delivery.drive`
New permission `delivery.drive`. Every driver endpoint (`open`, `me/run`, own depart/finish, own mark-delivered) requires `delivery.drive` **and** checks `run.employee_id == current_employee.id` (for run actions) or the delivery's run ownership (for mark-delivered). Dispatcher endpoints keep requiring `delivery.assign`/`delivery.manage`; a driver never gains those. `delivery.drive` is granted to the existing `courier` base role.
- *Why:* a courier acts only on their own work; dispatcher permissions are broader (any driver, any run) and inappropriate for a driver.
- *Alternative:* reuse `delivery.assign` with an ownership check — rejected: it also authorizes acting on *others'* runs and route/settings management by policy intent.

### D4 — Persist the not-delivered reason in a new nullable column
Extend `mark-delivered` to accept an optional `reason` (from the fixed list) + optional free-text `comment`, persisted in a new nullable `order_deliveries.not_delivered_reason` column (via additive migration). `notes` stays reserved for address/handling notes.
- *Why:* a dedicated field keeps the failure reason queryable and separate from address notes; additive + nullable = safe migration.
- *Alternative:* reuse `notes` — rejected: conflates two concerns and would clobber address notes.

### D5 — Frontend reconciliation of the real lifecycle
`depart` flips **all** the run's deliveries to `in_transit` at once, so per-stop state no longer distinguishes "next". The driver UI derives the "siguiente pedido" from `route_position` + terminal status (first non-terminal by position) — which is already how `StopRail`/`nextStop` works. `StatusPill` maps the real `assigned` (pre-depart) and `in_transit` (post-depart) states; "Abrir despacho" = self-open (create+pull); "Voy en camino"/depart is the run-level departure. `useDriverStore` moves from in-memory mutation to write-through (call API, refetch `me/run`), matching the dispatch store's discipline. `mockDriver.ts` is deleted; the geolocation "Tú" constant relocates/stays until Change 2.

## Risks / Trade-offs

- **Driver pull races with dispatcher assign** (both grab the same pending delivery) → the existing assign guard (delivery must be `pending`+unassigned, run `preparing`, same branch) makes the loser a no-op/conflict; pull skips already-assigned rows.
- **delivery → orders read coupling** → confine to a read-only application query returning a DTO; no schema/FK change, no write path.
- **Ownership bypass** (driver acts on another's run) → enforce `run.employee_id == me` on every driver endpoint; add tests for the 403/404 path.
- **Multi-route driver ambiguity on self-open** → if >1 active route, require an explicit route choice; if 0, reject with a clear "no route assigned" error.
- **Enriched read cost** (N deliveries × order join) → batch the order lookups (one query by `order_id in (...)`), not per-row.

## Migration Plan

1. Additive migration: `order_deliveries.not_delivered_reason` (nullable text). No backfill.
2. RBAC seed (additive, idempotent): add `delivery.drive` to the catalog, grant to `courier`. Re-runnable without disturbing tenant-custom roles.
3. Ship backend endpoints behind `delivery.drive`; dispatcher paths unchanged (backward compatible).
4. Frontend switch from mock to real; feature is inert for tenants with no `courier`/driver until a driver logs in.
5. Rollback: revoke `delivery.drive` grant + hide `/driver` wiring; the nullable column can remain unused.

## Open Questions

- On self-open with multiple active routes: pick-a-route UI now, or default to a "primary" route later?
tiene que cerrar un despacho para abrir otros, seria que ya entrego todos los pedidos, llega otra vez al restaurante y se coloca en disponible que es lo mismo de abrir otro despacho
- Pull scope: all branch pending-unassigned, or only the chosen route's zone? (Leaning route-scoped to avoid a driver vacuuming another route's drops.)
  No importa la zona, puede abrir su depacho y si esta en una zona se le agregan a su despacho enseguida
- Should a driver be allowed to *unassign* a wrongly-pulled delivery back to the pool before departing? (Probably yes — small follow-up.)
    yes
- Payment/`cobrar`: is cash-on-delivery collection recorded here, or does it stay a display-only figure until a cash-integration change?
  se debe registrar el pago, para llevar las finanzas y todo, para saber que si se pago 
