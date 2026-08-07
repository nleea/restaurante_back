# Cash station redesign — wire the `/cash/station` prototype to real data

## Why

The Caja screen was redesigned as an in-memory prototype at `/cash/station`: a live
POS-style cash station with two states (CERRADA / ABIERTA), a KPI cockpit, a movement
tape, a running arqueo docket, and a three-step cierre with a denomination counter. The
signature is El Pase's heat-lamp repurposed — the arqueo glows when it doesn't cuadre.

This change promotes that prototype to **the** Caja screen (the same path other redesigns
took: `/kds`→`/kitchen`, dispatch, inventory board), wiring it to the real backend.

The prototype imagines a full sales cockpit. In the real system that data is split across
three sources, and most of it already exists:

- **cash** — the drawer: apertura, manual in/out movements, running expected cash, arqueo.
- **reporting aggregation** — sales by channel, tickets, avg ticket, sales by method.
- **staff** — employee names/avatars for the pickers and movement authorship.

Two gaps block a faithful wiring today, both on the backend:

1. The movement `created_at` exists in the DB (`TimestampMixin`) but is **not serialized**
   in `CashMovementResponse` — so the feed has no time or stable ordering.
2. The live sales aggregates (KPIs, channel/method breakdown) are only available via the
   finance Z report, which is **spec'd for closed sessions and gated by `finance.read`** —
   but the cashier reaches the station with `cash.read`. Reusing it would break the
   permission model and the "live" requirement.

## What Changes

Path **B** (full cockpit). Backend additions are authorized.

**Backend (`cash-management`)**

- Expose `created_at` on `CashMovementResponse` (already stored).
- Add an optional `category` to cash movements (`entry` | `withdrawal` | `expense` |
  `sale` | `other`) so the feed and filter pills can distinguish retiro vs gasto vs
  entrada — `type` (in/out) alone cannot.
- Persist optional close observations: `notes` and `incident` (+ `incident_note`) on the
  session, set at close (cierre step 2).
- Add a **cash-scoped live shift summary** endpoint gated by `cash.read`, returning the
  open (or any) session's aggregates: sales total, tickets, avg ticket, sales by channel,
  sales by payment method, withdrawals, expected cash. This is the "live Z" for the drawer,
  without the `finance.read` gate or the closed-only limitation.

**Frontend (`frontend-cash`)**

- Replace the `/cash` screen with the station. `/cash/station` redirects to `/cash`.
- Wire the KPI cockpit (Zona A) and running summary (Zona C) to the new live-summary
  endpoint; degrade gracefully to the drawer-only view when it is unavailable.
- Wire the movement feed (Zona B) to `listMovements`, ordered by `created_at`, newest
  first, with category-based filter pills, refreshed by polling with new-row detection.
- Wire apertura, the register dialogs (entrada/retiro/gasto now carry `category`), and the
  three-step cierre (denomination counter → observations/incident → confirm), with the
  server-computed `expected`/`difference` driving the heat-lamp cuadre.
- Wire the historial master–detail to `listSessions` / `getSession` + per-session summary.

## Impact

- Specs: `cash-management`, `frontend-cash`.
- Backend: `cash` schemas/router/service/models + Alembic migration (`category`, close
  `notes`/`incident`, live-summary endpoint). No breaking changes to existing endpoints.
- Frontend: `views/CashStationView.vue` + `components/cashstation/*` swap from the in-memory
  `lib/cashStation.ts` to `stores/cash.ts` + `services/cash.api.ts` + a new summary call;
  router `/cash` remap; the old `CashView.vue` + `components/cash/*` are retired.

## Out of scope (deferred)

- **Orders → cash sale movements.** Sales do not appear as cash movements in the feed; the
  feed is the manual cash ledger (entradas/retiros/gastos). The automatic **sales tape** is
  deferred until the orders→cash integration lands — at which point sale movements
  (`category = sale`, `reference_id = order`) flow into the same feed with no UI change.
- Realtime push (SSE) for cash — polling is used now.
- Editing/voiding posted movements.
