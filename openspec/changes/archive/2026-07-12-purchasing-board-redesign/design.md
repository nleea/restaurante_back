## Context

Inventario shipped a board (`front/src/views/InventoryView.vue`, monolithic): header + area pill
tabs, a 4-KPI stats row (`.card .animate-docket`), a toolbar (search + Selects + list/cards toggle),
dismissable filter chips, a sortable table with the **depletion bar** (`h-1` track, colored fill,
notch at the minimum) + status pill + kebab menu, a card view, an alerts area, a bulk bar, a
`Teleport` right-side **detail drawer** with Detalles/Movimientos/Alertas tabs, an "Ajustar stock"
segmented modal, and a 2-step "Nuevo insumo" wizard. Design language ("El Pase") lives in
`front/src/assets/main.css`: tokens (`graphite-900`, `paper`, single accent `ember`, signals
`success/warn/info/alert`), reusable classes `.card`, `.eyebrow`, `.pill(-success/warn/alert/…)`,
`.animate-docket`, mono uppercase labels, active-tab `bg-ember text-graphite-900`.

Compras today is two thin master–detail screens:

- `/purchasing` → `PurchasingView.vue` → `SuppliersPanel.vue` + `SupplierDetail.vue` (suppliers +
  ingredient catalog; store `stores/purchasing.ts`, tenant-scoped).
- `/procurement` → `ProcurementView.vue` → `ProcurementPanel.vue` (requests/orders/receive/payments;
  store `stores/procurement.ts`, branch-scoped).

The backend and services are complete (`services/purchasing.api.ts`): suppliers, requests
(`pending/approved/rejected`), orders (`created/partially_received/received`) with per-item
`ordered_quantity`/`received_quantity`, receive (`POST /orders/{id}/receive` → inventory `in`
movement reason `purchase`), payments (`pending/partial/paid`). The procurement store already
derives **`receiptProgress`** (received/ordered/remaining/done) and **`outstandingBalance`** (total −
Σ payments) — the two figures a board needs, currently unsurfaced.

## Goals / Non-Goals

**Goals:**

- One Compras board at `/purchasing`, order-centric, in the approved board layout, running entirely
  on real branch-scoped data with existing permission gates.
- Reuse the store derivations as-is: `receiptProgress` → progress bar, `outstandingBalance` → por
  pagar figure and Pagos tab.
- Fold Solicitudes and Proveedores in as area tabs so Compras is a single destination.
- Retire the `/procurement` route and its panel once parity is verified; no dead second screen.
- Zero backend change.

**Non-Goals (explicit future work):**

- New backend endpoints, server-side filtering/pagination, or new migrations.
- Costing / margin and supplier-performance analytics (waits on canonical ingredient cost — the
  same C3 dependency Inventario deferred).
- Editing or cancelling a placed/received order.
- A dark theme, column-visibility popover, or import (cut in the Inventario board too).

## Decisions

1. **Orders are the spine; Solicitudes and Proveedores are area tabs.** The order list carries the
   depletion-bar analog (receipt progress) and the money signal (outstanding), so it earns the
   default view — exactly as Insumos is Inventario's default over Alertas. Requests feed orders;
   suppliers are a catalog. Three pill tabs (Órdenes / Solicitudes / Proveedores) mirror the
   Insumos/Alertas pattern.

2. **Reuse, don't rebuild, suppliers.** The Proveedores tab embeds the existing `SuppliersPanel.vue`
   / `SupplierDetail.vue` unchanged — supplier CRUD and the ingredient catalog are already correct;
   only their host moves from a standalone route into a board tab. This keeps the change focused on
   the orders experience and avoids re-testing supplier flows.

3. **Depletion bar → receipt-progress bar, one shared component.** Extract the Inventario bar into a
   small reusable bar (fill % + state color; notch optional) so the two boards read identically.
   Fill = `received/ordered`; state = creada / warn (partial) / success (received). Outstanding
   balance renders as a figure/pill, not a second bar, to avoid visual noise.

4. **Status buckets replace ok/low/out.** A `STATUS_META`-style map turns `ORDER_STATUSES` into
   `{label, pill, dot, bar}` classes; the same treatment gives payment state its pill. Stats,
   filters and alerts all read from these buckets — one loaded order list feeds everything (no
   double-fetch), matching Inventario's single-list discipline.

5. **Actions reuse the staff employee `Select`.** Recibir and Registrar pago take the registering
   employee from the staff store (active employees of the branch), the same control the Inventario
   stock modal uses. Deriving the employee from the logged-in user stays a separate product
   decision (users ≠ employees for admins).

6. **Non-atomic composites get partial-success copy.** "Nueva solicitud → aprobar → crear orden" is
   several real writes; on a mid-flow failure the board surfaces what remains ("solicitud creada,
   falta aprobar") and opens the drawer on the created record, rather than faking atomicity — the
   Inventario "Nuevo insumo" precedent.

7. **Stats, alerts and CSV compute from the loaded list** — no new endpoints. Client-side "por
   pagar" and status counts follow the Inventario/deliveries precedent until volume demands server
   support.

8. **Monolith or panel — reuse where cheap.** The Órdenes/Solicitudes board can extend
   `ProcurementPanel.vue` (which already loads requests/orders/payments) rather than a fresh
   monolith; the board chrome (header, tabs, stats, toolbar, chips, drawer) is new. Suppliers stay
   as their own components. Final structure is an implementation detail; parity and gates are the
   contract.

## Risks / Trade-offs

- [Permissions span three codes: view `purchasing.read`, receive/pay/create `purchasing.manage`,
  approve/reject `purchasing.approve`] → gate each control by its own permission; the board is
  reachable with `purchasing.read` alone and degrades to read-only.
- [Merging two routes into one board] → land the board behind `/purchasing` with `/procurement`
  redirecting; verify parity against seeded data before deleting `ProcurementView.vue` /
  `ProcurementPanel.vue`. Rollback = revert the frontend commit (no backend change to undo).
- [Receive/pay are non-atomic and money-touching] → ordered writes, friendly errors on 409/422
  (over-receive, no open cash session), write-through reload so the board reflects backend truth.
- [Two stores (tenant-scoped suppliers, branch-scoped procurement) behind one screen] → the board
  loads each area's store on tab activation; no shared state is invented.

## Migration Plan

1. Build the board behind `/purchasing` reusing the procurement store + panel and embedding the
   suppliers components as the Proveedores tab; keep `/procurement` working during development.
2. Verify end-to-end against seeded data (orders with partial/full receipts show correct bars and
   stats; receive updates progress and stock; payments reduce outstanding; approve/reject gated;
   read-only without manage/approve; filters, chips and CSV).
3. Swap: `/purchasing` renders the board, `/procurement` redirects to it, delete
   `ProcurementView.vue` and `ProcurementPanel.vue`. Rollback = revert the frontend commit.

## Open Questions

None blocking. Deferred explicitly: costing/margin & supplier-performance (C3-equivalent),
order edit/cancel, server-side filtering/pagination.
