# Design — cash station redesign

## Context

The redesign prototype (`views/CashStationView.vue`, `components/cashstation/*`,
`lib/cashStation.ts`) is complete and self-contained in memory. This change replaces the
in-memory model with the real backend while keeping the visual design intact. The design
question is not "how does it look" but "where does each figure come from, and what must the
backend add so the cashier (holding only `cash.read`) can see it live."

## The three data sources

```
   STATION ELEMENT                         SOURCE                         GATE
   ─────────────────────────────────────────────────────────────────────────────
   Estado CERRADA / ABIERTA          cash  getOpenSession (404=none)      cash.read
   Apertura (empleado + fondo)       cash  openSession                    cash.open
   Efectivo estimado en caja         cash  store.runningExpectedCash      cash.read
   Feed de movimientos               cash  listMovements (+created_at)    cash.read
   Cierre → expected/difference      cash  closeSession (server computes) cash.close
   Historial + arqueo detalle        cash  listSessions / getSession      cash.read
   ─────────────────────────────────────────────────────────────────────────────
   KPIs: ventas / tickets / prom.  ▶ NEW cash live shift summary          cash.read
   Zona C: canal + método          ▶ NEW cash live shift summary          cash.read
   ─────────────────────────────────────────────────────────────────────────────
   Empleado (nombre / iniciales)     staff employeeName()                 staff.read
```

## Decision: a cash-scoped live summary, not `/reports/z`

The sales aggregates the cockpit needs (gross sales, tickets, avg ticket, `channels[]`,
`payments[]`, withdrawals) are exactly what `GET /reports/z/{cash_session_id}` already
computes. Reusing it was the first instinct. Rejected because:

- **Permission mismatch.** The Z report requires `finance.read`; the station is reached
  with `cash.read`. A cashier without finance access could not load their own KPIs.
- **Closed-only semantics.** The finance-reporting spec describes the Z report *for a
  closed cash session*; live computation over an open session is not a guaranteed contract.
- **Capability boundary.** The station is a cash screen; its live numbers should belong to
  the cash capability, not depend on finance's gate.

**Decision:** add `GET /cash/sessions/{session_id}/summary` (and/or
`GET /cash/branches/{branch_id}/open-session/summary`), gated by `cash.read`, returning the
open (or any) session's aggregates. It MAY reuse the reporting aggregation internally
(compute over the session's time window and branch), but it is exposed under `cash` with the
`cash.read` gate and is defined to work for an **open** session. Response shape mirrors the
Z report's sales section:

```
{ sales_total, tickets, avg_ticket,
  channels: [{ channel, amount, tickets }],
  payments: [{ method, amount }],
  withdrawals, expected_cash }
```

Graceful degradation: if the endpoint 404s / errors (e.g. a branch with no orders module
data), the station renders the drawer-only view (apertura, movements, expected cash,
arqueo) and hides the KPI strip + channel/method breakdown. The drawer is always truthful
from cash alone.

## Decision: `category` on movements

`type` is only `in`/`out`. Retiro and gasto are both `out` and indistinguishable, so the
filter pills (Ventas/Retiros/Gastos/Entradas) and the row semantics need more. Options
considered: (a) a naming convention in `concept` — fragile, breaks i18n; (b) infer from
`method` — wrong axis; (c) a real `category` column — chosen. Values:
`entry | withdrawal | expense | sale | other`. Optional and defaulted so existing rows and
callers keep working; `type` remains the source of truth for the drawer math.

## Decision: three-step cierre persistence

The denomination counter is pure UI — it only produces `counted_amount`, which the existing
`closeSession` already accepts; no backend change needed for step 1 or 3. Step 2
(observaciones + incidente) has nowhere to live today. We add optional `notes`, `incident`
(bool), and `incident_note` to the session, written at close. The heat-lamp cuadre keys off
the server-computed `difference` (0 = calm, `<10k` = warm ember, `≥10k` = breathing red).

## Decision: polling, not SSE

Cash has no realtime channel (KDS does). "En vivo" is served by polling `listMovements` (and
the summary) on an interval while a session is open, diffing by movement `id` to flash new
rows. SSE for cash is a separate, larger change; not needed for this slice.

## Deferred boundary: orders → cash

The feed is the **manual cash ledger**, not a sales tape. Sales are aggregated in the KPIs
(via the summary endpoint) but do not appear as individual movements, because the orders→cash
integration (an order payment writing a `sale` cash movement) is out of scope and being
waited on. The design keeps the door open: `category = sale` + `reference_id = order` already
fit the movement model, so when that integration lands, sale movements flow into the same
feed and the same filter pill with no further UI work.

## Risks / assumptions to verify

- **[verify] Live summary over an open session.** Confirm the reporting aggregation can be
  computed for an open session's window (opened_at → now) and returns sane numbers before a
  close exists. If the current aggregation hard-filters to closed sessions, extend it.
- **[verify] Seed/demo data.** `seed_demo` should produce a branch with an open session +
  orders so the cockpit shows non-zero KPIs in dev.
- **[assumption] `runningExpectedCash` stays cash-only** and remains labelled an estimate;
  the authoritative expected/difference still come from the server at close. Unchanged.
- **[assumption] No breaking changes.** `created_at`, `category`, and close `notes` are
  additive; existing clients ignore them.
