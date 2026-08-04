## 1. Service layer

- [x] 1.1 Create `front/src/services/cash.api.ts` with types `CashSession` and `CashMovement` (money fields typed as `string`, matching backend schemas)
- [x] 1.2 Add session calls: `openSession(input)` (`POST /cash/sessions`), `listSessions(branchId)` (`GET /cash/sessions`, branch_id query param), `getOpenSession(branchId)` (`GET /cash/branches/{branchId}/open-session`), `getSession(id)` (`GET /cash/sessions/{id}`), `closeSession(id, input)` (`POST /cash/sessions/{id}/close`)
- [x] 1.3 Add movement calls: `registerMovement(sessionId, input)` (`POST /cash/sessions/{id}/movements`), `listMovements(sessionId)` (`GET /cash/sessions/{id}/movements`)
- [x] 1.4 Add service unit tests in `front/src/services/__tests__/cash.api.spec.ts` (URLs, payloads, branch_id param, returned shapes)

## 2. Store layer

- [x] 2.1 Create `front/src/stores/cash.ts` (Pinia options) state: `currentSession`, `currentMovements`, `history`, `selectedSessionId`, `selectedSession`, `selectedMovements` (open session named `currentSession` to avoid colliding with the `openSession` action)
- [x] 2.2 Add `loadBranchCash(branchId)` — fetch open session (map 404 to `currentSession = null`, not an error) and its movements
- [x] 2.3 Add `loadHistory(branchId)` and `selectSession(id)` (load session detail + its movements)
- [x] 2.4 Add `openSession(input)` action (write-through: set open session, clear ledger)
- [x] 2.5 Add `registerMovement(input)` action (write-through: refetch the open session's movements)
- [x] 2.6 Add `closeSession(input)` action (write-through: clear open session, refetch history, select the closed session so its reconciliation shows in the detail pane)
- [x] 2.7 Add `runningExpectedCash` getter — `opening_amount + Σ(cash in) − Σ(cash out)` over `method === 'cash'` only, computed in integer cents; add `hasOpenSession` and `movementsByMethod` getters
- [x] 2.8 Add store unit tests: open-session-as-none (404), movement/close write-through refetch, running expected cash including the cash-only exclusion and integer-cents arithmetic

## 3. Screen, components, routing

- [x] 3.1 Add `/cash` route (name `cash`, `meta.permission: 'cash.read'`) in `front/src/router/index.ts` and a nav link (`Caja`) in `front/src/components/AppSidebar.vue`
- [x] 3.2 Create `front/src/views/CashView.vue` container + `CashPanel.vue` orchestrator: active-branch guard, switch between Sesión actual / Abrir caja (by `hasOpenSession`) and Historial
- [x] 3.3 Create the Abrir caja component (gated by `cash.open`): employee picker (reuse staff store) + opening float; friendly handling of the "ya hay una caja abierta" conflict
- [x] 3.4 Create the Sesión actual component: opening float, movement ledger (grouped/badged by method), and the running expected-cash figure labelled as estimate
- [x] 3.5 Create the Registrar movimiento control (gated by `cash.move`): type in/out, concept, positive amount, method; hidden when no session is open
- [x] 3.6 Create the Cerrar caja (arqueo) control (gated by `cash.close`): employee picker + counted amount, then show server `expected_amount` and signed `difference` (surplus/shortfall)
- [x] 3.7 Create the Historial component: list branch sessions + detail pane showing opening/expected/counted/difference and the session's movements
- [x] 3.8 Add a manual refresh affordance and surface API errors with friendly messages (reuse `apiError` helpers); render all money via `formatCOP`

## 4. Verification

- [x] 4.1 `pnpm type-check` and `pnpm lint` clean (also `pnpm build` succeeds with the cash module bundled)
- [x] 4.2 `pnpm test:unit` green (87 tests across 15 files, incl. new cash service + store tests)
- [ ] 4.3 Manual smoke against the running backend: abrir caja → registrar cash + non-cash movements (verify only cash moves the expected figure) → cerrar con arqueo (verify expected/difference) → review in Historial; verify a read-only user sees no apertura/movimiento/arqueo controls
