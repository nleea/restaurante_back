## 1. Backend

- [x] 1.1 Read: list a branch's closed cash sessions, most recent first — reuses existing `GET /cash/sessions?branch_id=&status_filter=closed`
- [x] 1.2 Read: a session's operational record — orders/deliveries filtered by `cash_session_id` (deliveries via their order). NOTE: payments/tickets stay in the Reporte Z (money lens); the record is the operational lens (orders + deliveries) to avoid redundancy
- [x] 1.3 Exclude null-session rows (join/filter drops pre-boundary data). NOTE: pagination deferred — a single shift's order/delivery count is bounded; returns all for now
- [x] 1.4 Expose endpoint under the reporting surface (`GET /reports/shift/{cash_session_id}`)

## 2. Backend — tests

- [x] 2.1 Closed-sessions list — reuses the existing, already-tested cash `list_sessions` (status filter)
- [x] 2.2 Session record aggregates the right orders/deliveries; excludes null-session rows
- [x] 2.3 Empty/unknown session — unknown session 404s; an empty shift returns `{orders:[], deliveries:[]}` cleanly

## 3. Frontend

- [x] 3.1 "Registros por turno" list — the Finanzas Reporte Z tab already lists (closed) sessions (master)
- [x] 3.2 Session detail: operational record card beside the Reporte Z (orders + deliveries for the selected session)
- [x] 3.3 Empty state (card hidden when empty, no error); api-layer test for `getShiftRecord`

## 4. Validation

- [x] 4.1 Backend tests + ruff + mypy
- [x] 4.2 Frontend type-check, unit tests, lint, build
- [x] 4.3 `openspec validate shift-history-records --strict` passes
