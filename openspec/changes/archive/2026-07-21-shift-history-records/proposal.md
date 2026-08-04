## Why

Once a cash session closes, its orders/deliveries/tickets drop off the live boards ([[cash-session-operating-shift]]). Staff still need to review them — to reconcile, do cruces, and build reports — grouped by the shift they belonged to, the same way the Reporte Z groups the money. Today there is no per-closed-session operational record view.

## What Changes

- Add **per-closed-session operational records**: list past (closed) sessions, and for a session show its orders, deliveries, kitchen tickets and payments — the operational companion to the financial Reporte Z.
- Records are read-only history, queryable by `cash_session_id`, enabling cross-references (e.g. deliveries vs collected, tickets vs sold) and report exports.

Out of scope (separate proposals): the operating-shift gate/stamp ([[cash-session-operating-shift]]); the pre-close pending summary ([[cash-close-pending-summary]]); opening-hours/profile.

## Capabilities

### Modified Capabilities
- `finance-reporting`: add per-closed-session operational records (orders/deliveries/tickets/payments by session), alongside the existing Reporte Z, to support cruces and reports.
- `frontend-finance-reporting`: a "Registros por turno" view that lists closed sessions and drills into a session's operational record.

## Impact

- **Backend**: history reads scoped by `cash_session_id` (now available on orders, inherited by deliveries/tickets) — list closed sessions for a branch, and aggregate a session's operational record. Read-only; no schema change.
- **Depends on** [[cash-session-operating-shift]] (session anchor) and complements [[cash-close-pending-summary]].
- **Frontend**: new records view under Finanzas, reusing the Reporte Z framing (per-session docket) for the operational record.
