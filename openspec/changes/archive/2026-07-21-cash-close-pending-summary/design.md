## Context

`CashService.close_session` validates only the counted amount and computes cash totals; it does not look at orders or deliveries. Once orders carry `cash_session_id` ([[cash-session-operating-shift]]), a session's operational work is queryable. The user wants closing to warn about unresolved work but never block a force-close (test data).

## Goals / Non-Goals

**Goals:**
- Show, before closing, the session's uncollected orders and undelivered deliveries.
- Keep force-close always available.

**Non-Goals:**
- Blocking or auto-resolving pending items.
- Changing the arqueo/cash-difference computation.
- Per-session history browsing (separate change).

## Decisions

**1. Advisory summary, never a hard gate.**
The close endpoint keeps its current behavior; a separate preview computes the pending summary. The UI shows it and asks for confirmation, but the backend does not reject a close with pending items.
*Alternative considered:* block close until resolved. Rejected — the user explicitly wants force-close; blocking would trap staff at end of shift.

**2. "Pending" = unpaid-remainder orders + non-delivered deliveries, scoped by session.**
Reuse the existing unpaid-remainder rule (from order close-requires-payment) for "uncollected", and delivery status ≠ delivered for "undelivered". Both filtered by the session's orders (`cash_session_id`).
*Alternative considered:* a new "pending" flag column. Rejected — derivable from existing state; no new writes.

**3. Preview surface: a GET the close screen calls.**
A `GET` returning `{uncollected: {count, total}, undelivered: {count}}` for the open session. The UI shows it on entering the close/arqueo screen.
*Alternative considered:* fold into the close response. Rejected — the user must see the summary BEFORE deciding to close.

## Risks / Trade-offs

- **Force-close leaves real pending work unresolved** → acceptable now (test data, explicit user choice); a future change could add settle-on-close. Mitigation: the summary makes the consequence visible.
- **Summary/close race** (item settled between preview and close) → harmless; the summary is advisory and re-fetchable.

## Migration Plan

1. Backend: add the pending-summary read (reuse unpaid-remainder + delivery status), scoped by session; expose via preview endpoint.
2. Frontend: arqueo/close screen fetches and displays it, with "Cerrar de todos modos".
3. No schema change; no rollback data concerns.

## Open Questions

- Should "uncollected" count fiado (customer credit) closes as resolved or pending? Default: a fiado close is resolved (credit is an accepted settlement), consistent with order close-requires-payment.
