## Context

The backend `/cash` module is complete but unconsumed. Its contract:

- **Sessions**: `POST /cash/sessions` (`cash.open`) → opens with
  `{ branch_id, opened_by_employee_id, opening_amount }`; `GET /cash/sessions` (`cash.read`) lists;
  `GET /cash/branches/{branch_id}/open-session` (`cash.read`) returns the branch's single open
  session or 404; `GET /cash/sessions/{session_id}` (`cash.read`); `POST /cash/sessions/{id}/close`
  (`cash.close`) with `{ closed_by_employee_id, counted_amount }`.
- **Movements**: `POST /cash/sessions/{id}/movements` (`cash.move`) with
  `{ type: "in"|"out", concept, amount, method, reference_id? }`; `GET /cash/sessions/{id}/movements`
  (`cash.read`).
- `CashSession = { id, branch_id, opened_by_employee_id, opening_amount, status, opened_at,
  closed_by_employee_id, counted_amount, expected_amount, difference, closed_at }`.
- `CashMovement = { id, branch_id, cash_session_id, type, concept, amount, method, reference_id }`.
- Money fields are server-side `Decimal`, serialized as **strings** ("23900.00").

Three facts drive the design: (1) the lifecycle is a **state machine** — a branch has at most one
`open` session; everything (movements, close) hangs off that session, so the screen's primary axis
is "is there an open session?"; (2) **reconciliation is cash-only** — the backend's `expected_amount`
counts `method = cash` movements against the float and ignores card/Nequi/Daviplata, so the UI must
make the cash-vs-other distinction legible; and (3) open/close require an **employee id**, so the
screen reuses staff data for a picker. The frontend stack and conventions follow the existing
screens (Vue 3 `<script setup>`, Pinia options stores, PrimeVue + Tailwind, the shared `@/lib/http`
axios instance, active-branch scope, `formatCOP`, mobile-first master–detail as in Orders/Kitchen).

## Goals / Non-Goals

**Goals:**
- A self-sufficient daily cash control: abrir caja (float), registrar movimientos in/out, ver el
  efectivo esperado en vivo, and cerrar con arqueo (counted → expected/difference) — all from one
  branch-scoped screen.
- Surface the cash-only reconciliation rule clearly, both in the live running figure and at close.
- Reuse existing staff/branch/money/error infrastructure and the established store discipline
  (write-through, `can()` gating) rather than new patterns.

**Non-Goals:**
- The orders→cash payment integration (an order payment writing a `sale` movement) — separate change
  per the backend capability's stated scope.
- Realtime/push or auto-refresh (manual refresh this slice); editing or voiding posted movements;
  multi-currency; printed/Z-report output and cross-shift analytics.

## Decisions

**1. One `CashView`, state-driven, with three areas.** The view's spine is the active branch's open
session. When one exists it shows **Sesión actual** (float, ledger, running expected cash, +
movimiento, + cerrar); when none exists that area becomes the **Abrir caja** form. A persistent
**Historial** area lists the branch's sessions with a detail pane. One cohesive screen (not separate
config/report screens) keeps a fresh branch usable and mirrors the Kitchen "one view, gated areas"
decision. Rejected: a wizard/modal-only flow — it hides the ledger that cashiers watch all shift.

**2. Money stays string-decimal end to end; arithmetic is integer-cents.** Service types carry
`amount`/`opening_amount`/etc. as `string` exactly as the backend sends them, and `formatCOP`
renders them. The only client-side arithmetic is the running expected cash; to avoid float drift it
sums in integer cents (parse → cents → sum → format), never `parseFloat` accumulation. The
authoritative `expected_amount`/`difference` always come from the server at close — the client
figure is labelled guidance only. Rejected: client-computing the closed reconciliation (would risk
disagreeing with the server of record).

**3. Running expected cash replicates the backend's cash-only rule, client-side.** A getter computes
`opening_amount + Σ(cash in) − Σ(cash out)` over movements with `method === 'cash'`, ignoring other
methods, so the cashier sees the drawer figure they'll be counting against before they commit a
count. Non-cash movements still render in the ledger (grouped/badged by method) but are excluded
from the figure, making the rule visible rather than surprising at close. This is the cash analogue
of Kitchen's client-side label/column derivations.

**4. Employee picker reuses staff data.** `opened_by_employee_id` / `closed_by_employee_id` are
chosen from the staff store's active-branch employees (load on demand, same `ensureLoaded` pattern).
No new endpoint. If staff isn't loaded the picker triggers its load; an empty staff list surfaces a
friendly "no hay empleados" hint rather than a broken submit.

**5. Store shape parallels `orders.ts`/`kitchen.ts`.** State: `openSession: CashSession | null`,
`movements: CashMovement[]` (for the open session), `sessions: CashSession[]` (history),
`selectedSessionId`, `selectedMovements`. Getters: `hasOpenSession`, `runningExpectedCash`,
`movementsByMethod` (ledger grouping). Actions (each write-through): `loadBranchCash(branchId)`
(fetches open-session — tolerating 404-as-none — and its movements), `loadHistory(branchId)`,
`openSession(input)`, `registerMovement(input)` (refetch movements), `closeSession(input)` (clear
open session, refetch history), `selectSession(id)` (load detail + its movements). The open-session
404 is caught and mapped to `openSession = null`, not propagated as an error.

**6. Permission model mirrors existing screens.** Route guard `meta.permission: 'cash.read'`; within
the view, `auth.can('cash.open' | 'cash.move' | 'cash.close')` gates each mutate control
independently, so a read-only user sees the drawer and history without action affordances. The
backend enforces the same permissions regardless.

## Risks / Trade-offs

- **Client running-cash could disagree with the server at close** → Mitigation: compute it with the
  exact cash-only rule in integer cents and label it "esperado (estimado)"; the close response's
  `expected_amount`/`difference` are shown as authoritative and override the estimate.
- **Stale open-session view** (a movement added on another device) → Mitigation: write-through
  refetch after local actions plus a manual refresh control; no realtime this slice (deliberate,
  matches Kitchen).
- **`method` is a free-form string (1–30 chars) backend-side** → the UI offers a known set
  (cash/card/Nequi/Daviplata) but only `cash` drives reconciliation; an unexpected method value from
  history still renders (badged as "otro") and is excluded from the cash figure. → Mitigation:
  treat any non-`cash` method as non-drawer, never crash on an unknown string.
- **Open/close need a valid employee id** → an empty staff list blocks apertura → Mitigation:
  surface a clear hint and link expectation to the staff screen rather than a silent disabled button.

## Migration Plan

Pure additive frontend change; no backend deploy, no data migration. Ship behind existing
`cash.read` / `cash.open` / `cash.move` / `cash.close` permissions. Rollback = revert the new files,
the router entry, and the nav link; no persisted client state.

## Open Questions

- Should the history list be paginated/date-filtered? Deferred — the pilot's session volume is low;
  `GET /cash/sessions` returns the branch set and the client can filter by status for now.
- Should a movement offer a "linked reference" (`reference_id`)? The field is accepted but optional
  and loose; left unbound in the UI this slice (no producer for it until the orders→cash change).
