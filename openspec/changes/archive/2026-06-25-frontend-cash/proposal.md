## Why

The backend `/cash` module — branch-scoped register sessions with an open/close (arqueo)
lifecycle and an in/out movement ledger — has no frontend, so a cashier cannot open a drawer,
record cash in/out during a shift, or close with reconciliation from the UI. This is the next
operational screen after orders/cobro and kitchen: it closes the money loop by giving the branch
a daily cash control (apertura, movimientos, arqueo) and is a prerequisite for finance reporting.

## What Changes

- Add a **Cash service layer** (`cash.api.ts`) over `/cash`: open a session
  (`POST /cash/sessions`), list sessions (`GET /cash/sessions`), get the branch's current open
  session (`GET /cash/branches/{branch_id}/open-session`), get a session by id
  (`GET /cash/sessions/{session_id}`), close a session
  (`POST /cash/sessions/{session_id}/close`), register a movement
  (`POST /cash/sessions/{session_id}/movements`), and list a session's movements
  (`GET /cash/sessions/{session_id}/movements`).
- Add a **Cash store** (`cash.ts`): the active branch's current open session (or none), that
  session's movements, the session history list, plus a client-side **running expected cash**
  derived from the opening amount and `method = cash` in/out movements — guidance shown before the
  cashier commits a counted amount at close.
- Add the **CashView** screen with three areas, mobile-first per the house master–detail pattern:
  - **Sesión actual** (cashier-facing): when the branch has an open session, show its opening
    float, the movement ledger, and the running expected cash; offer **registrar movimiento**
    (in/out, concept, amount, method) gated by `cash.move` and **cerrar caja (arqueo)** — enter the
    counted cash, then show `expected_amount` / `difference` from the server — gated by `cash.close`.
    When there is no open session, show an **abrir caja** form (employee + opening float) gated by
    `cash.open`.
  - **Historial**: list past sessions for the branch (optionally by status); selecting one shows
    its reconciliation result (opening, expected, counted, difference) and its movements.
- Reuse the **staff** data to pick `opened_by_employee_id` / `closed_by_employee_id`, the
  active-branch context, `formatCOP`, and the `apiError` helpers.
- Add the **route + nav entry** (`/cash`, permission `cash.read`) and a navigation link.
- Unit tests for the service and store (URLs/payloads, write-through refetch, and the running
  expected-cash derivation including the cash-only rule).

Non-goals: the orders→cash payment integration (an order payment writing a `sale` movement) — a
separate change per the backend capability's scope; realtime/push or auto-refresh (manual refresh
this slice); editing or voiding a posted movement; multi-currency; printed/Z-report output and
cross-shift analytics.

## Capabilities

### New Capabilities
- `frontend-cash`: the cash-register frontend — open a branch session with a float, record in/out
  movements during the shift, view the live expected-cash guidance, and close with reconciliation
  (arqueo), plus a session history with reconciliation detail, all scoped to the active branch and
  gated by `cash.read` / `cash.open` / `cash.move` / `cash.close`.

### Modified Capabilities
<!-- None. Consumes the existing cash-management backend unchanged; no requirement-level changes
     to other capabilities (the orders→cash payment movement is explicitly out of scope). -->

## Impact

- **Frontend code**: new `front/src/services/cash.api.ts`, `front/src/stores/cash.ts`,
  `front/src/views/CashView.vue`, and `front/src/components/cash/*`; a route in
  `front/src/router/index.ts` and a nav link in `front/src/components/AppSidebar.vue`. New tests
  under `front/src/services/__tests__` and `front/src/stores/__tests__`.
- **Reuses**: the staff store (employee picker for open/close), the active-branch context, the
  shared `http` axios instance, `@/lib/money` `formatCOP`, and the `apiError` helpers.
- **Backend**: none — consumes existing `/cash` endpoints
  (`cash.read` / `cash.open` / `cash.close` / `cash.move`).
- **Permissions/RBAC**: relies on `cash.read` (screen + read), `cash.open` (apertura),
  `cash.move` (movimientos), `cash.close` (arqueo); no new permission codes.
- **Dependencies**: no new packages; PrimeVue + Tailwind + Axios as elsewhere.
