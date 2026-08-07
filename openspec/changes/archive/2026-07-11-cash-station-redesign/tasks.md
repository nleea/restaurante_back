# Tasks — cash station redesign

## Backend — cash-management

- [x] Add `created_at` to `CashMovementResponse` (schema) and confirm the repo/model returns it
- [x] Add `category` to `CashMovementModel` (`String(20)`, nullable/defaulted) + Alembic migration
- [x] Accept `category` in `RegisterMovementRequest` and thread it through service → entity → repo
- [x] Add `notes`, `incident` (bool), `incident_note` to `CashSessionModel` + migration
- [x] Accept the close observations in `CloseSessionRequest` and persist them in `close_session`
- [x] Add live shift summary endpoint `GET /cash/sessions/{session_id}/summary` (and open-session
      variant) gated by `cash.read`; returns sales_total, tickets, avg_ticket, channels[],
      payments[], withdrawals, expected_cash
- [x] Implement the summary via the reporting aggregation over the session window (branch +
      opened_at→now); verify it computes for an OPEN session
- [x] Tests: movement `created_at`/`category` round-trip; close persists observations; summary
      returns correct aggregates for an open and a closed session; `cash.read` gate enforced
- [x] `ruff check`, `mypy src`, `pytest` green; `seed_demo` yields an open session with orders

## Frontend — services & store

- [x] Extend `services/cash.api.ts`: `created_at` + `category` on `CashMovement`; `category` on
      `RegisterMovementInput`; `notes`/`incident` on `CloseSessionInput`; `getSessionSummary()`
- [x] Extend `stores/cash.ts`: hold `currentSummary`; load it with the open session; expose a
      `refresh()` for polling; keep `runningExpectedCash` as the cash-only estimate
- [x] Adapter helpers: movement `kind`/icon/detail derived from `type` + `category` + `concept`;
      employee name via the staff store

## Frontend — station wiring (replace in-memory model)

- [x] Repoint `views/CashStationView.vue` + `components/cashstation/*` from `lib/cashStation.ts`
      to the store/services (keep the visual design and the heat-lamp cuadre intact)
- [x] Zona A KPIs + Zona C summary ← `currentSummary`; hide + degrade to drawer-only when absent
- [x] Zona B feed ← `listMovements` ordered by `created_at` desc; category filter pills; polling
      with new-row flash by `id` diff
- [x] Apertura ← `openSession` (employee UUID from picker, not name)
- [x] Register dialogs pass `category` (entry/withdrawal/expense); enforce concept ≤ 50 chars
- [x] Cierre: denomination counter → `counted_amount`; step 2 → `notes`/`incident`; confirm →
      `closeSession`; heat-lamp keys off server `difference`
- [x] Historial master–detail ← `listSessions` / `getSession` (+ per-session summary for detail)
- [x] Permission gating: apertura/movimiento/arqueo by `cash.open`/`cash.move`/`cash.close`
- [x] Router: `/cash` → `CashStationView`; `/cash/station` redirects to `/cash`; retire
      `CashView.vue` + `components/cash/*` + `lib/cashStation.ts`
- [x] `pnpm type-check`, `pnpm lint`, `pnpm build` green

## Verification

- [x] Run backend + `demo.localhost`; open a caja, register entrada/retiro/gasto, watch KPIs +
      summary + feed update; close via the 3-step arqueo; confirm it lands in historial with the
      correct signed difference and cuadre heat state
- [x] Read-only user (`cash.read` only) sees the station without apertura/movimiento/arqueo
      actions and still gets KPIs (summary is `cash.read`)
