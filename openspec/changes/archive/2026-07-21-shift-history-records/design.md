## Context

With orders stamped by `cash_session_id`, every closed session has a well-defined set of orders (and, via them, deliveries/tickets/payments). The Reporte Z already presents a closed session's money; this adds the operational record for the same session so staff can cross-check and report.

## Goals / Non-Goals

**Goals:**
- Browse closed sessions and open a session's operational record (orders/deliveries/tickets/payments).
- Enable cruces (deliveries vs collected, sold vs prepared) and report exports.

**Non-Goals:**
- New aggregates the Reporte Z already covers (cash difference, denominations).
- Editing history — it is read-only.
- Live-board behavior (that is the operating-shift change).

## Decisions

**1. History is a read model keyed by `cash_session_id`.**
No new tables; queries filter existing orders/deliveries/tickets/payments by session. Deliveries/tickets resolve their session via the order.
*Alternative considered:* denormalized per-session snapshot on close. Rejected — the source rows are immutable once the session is closed; a snapshot would duplicate them.

**2. Records view sits beside Reporte Z, reusing its per-session docket framing.**
The Z is the financial page; "Registros por turno" is the operational page for the same session id. One session → two lenses.

**3. List closed sessions per branch, most recent first; drill into one.**
Master–detail like the rest of the app (list of closed sessions → a session's record).

## Risks / Trade-offs

- **Large sessions = heavy reads** → paginate the per-session order/delivery lists; the closed-session list is naturally bounded.
- **Sessions with null-session legacy rows** → excluded (they belong to no session), consistent with the operating-shift change.

## Migration Plan

1. Backend: read endpoints — list closed sessions (branch), and a session's operational record (orders/deliveries/tickets/payments), all by `cash_session_id`.
2. Frontend: "Registros por turno" list + session detail under Finanzas.
3. No schema change; no rollback data concerns.

## Open Questions

- Export format for reports/cruces (CSV vs on-screen only)? Default: on-screen record first; CSV export as a fast follow.
- Do we need cross-branch consolidated records now, or per-branch only? Default: per-branch (consolidated multi-branch reporting is a later phase per project constraints).
