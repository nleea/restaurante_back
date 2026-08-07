## Why

Closing a cash session today only counts money (`close_session` computes cash totals and closes) — it never checks operational state. With the open session now defining the operating shift ([[cash-session-operating-shift]]), closing it should first show what is still unresolved: orders not fully collected and deliveries still out. The user's rule: **warn, don't block** — surface the pending items but let staff force-close anyway (all current data is test data).

## What Changes

- Add a **pending summary** for the open session: orders with an unpaid remainder (uncollected) and deliveries not yet delivered, scoped to that session.
- Expose the summary as a **preview** the close/arqueo UI shows before committing, so the person closing sees "hay N pedidos sin cobrar · M domicilios sin entregar".
- **Force-close stays allowed**: closing is never blocked by pending items; the summary is advisory only.

Out of scope (separate proposals): the per-session history/records view; opening-hours; the order-creation gate (already in [[cash-session-operating-shift]]).

## Capabilities

### Modified Capabilities
- `cash-management`: closing a session SHALL be preceded by an available pending summary (uncollected orders + undelivered deliveries for the session); closing is advisory-gated only (never blocked).
- `frontend-finance`: the arqueo/close flow SHALL show the pending summary and a "Cerrar de todos modos" confirmation.

## Impact

- **Backend**: a read that computes, for the open session, count/total of orders with unpaid remainder and count of deliveries not in a delivered state; exposed via a preview endpoint (or folded into the get-open-session response). Reuses the existing unpaid-remainder logic (order close-requires-payment) and delivery status.
- **Depends on** [[cash-session-operating-shift]] — "the session's orders/deliveries" is only well-defined once orders carry `cash_session_id`.
- **Frontend**: arqueo close screen renders the summary + force-close confirmation.
- **No change** to the close computation itself (cash totals, arqueo difference) — this only adds an advisory pre-close view.
