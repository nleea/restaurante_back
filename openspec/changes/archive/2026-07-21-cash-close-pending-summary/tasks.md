## 1. Backend

- [x] 1.1 Add a pending-summary read for an open session: uncollected orders (count + total unpaid remainder) and undelivered deliveries (count), scoped by `cash_session_id`
- [x] 1.2 Reuse the existing unpaid-remainder rule (order close-requires-payment) and delivery status ≠ delivered
- [x] 1.3 Expose a preview endpoint returning the summary for the branch's open session
- [x] 1.4 Confirm `close_session` remains non-blocking (no new rejection for pending items)

## 2. Backend — tests

- [x] 2.1 Summary counts uncollected orders + undelivered deliveries for the session; zero when clean
- [x] 2.2 Close succeeds with pending items present (force-close path unaffected)
- [x] 2.3 Fiado (credit) close counts as resolved, not pending

## 3. Frontend

- [x] 3.1 Arqueo/close screen fetches + shows the pending summary on entry
- [x] 3.2 Require an explicit "Cerrar de todos modos" confirmation when pending > 0; plain close when clean
- [x] 3.3 Frontend tests: summary rendered; force-close confirmation gating

## 4. Validation

- [x] 4.1 Backend tests + ruff + mypy
- [x] 4.2 Frontend type-check, unit tests, lint, build
- [x] 4.3 `openspec validate cash-close-pending-summary --strict` passes
