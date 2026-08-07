# Tasks — purchasing-board-redesign

## 1. Stores: board helpers (no backend change)

- [x] 1.1 `stores/procurement.ts`: add board getters over the loaded branch orders — status buckets
  (creada/parcial/recibida), distinct-suppliers getter, stats (counts by status + total `por
  pagar` from `outstandingBalance`), and a per-order `receiptProgress`-derived fill/state helper;
  unit tests
- [x] 1.2 `stores/purchasing.ts`: expose whatever the Proveedores tab needs unchanged (suppliers +
  catalog already there); confirm `supplierName`/`ingredientLabel` label getters are reusable by
  the orders board; no behavior change
- [x] 1.3 Confirm `services/purchasing.api.ts` covers every board read/write (orders, items,
  receive, payments, requests, approve/reject) — no new endpoints; add service tests only if a
  gap surfaces

## 2. Shared board pieces

- [x] 2.1 Extract the receipt-progress bar as a small reusable component (fill % + state color,
  optional notch) so Órdenes rows/cards/drawer read like the Inventario depletion bar
- [x] 2.2 `STATUS_META`-style maps for order status and payment status → `{label, pill, dot, bar}`
  El Pase classes; row-tint helper by state

## 3. Compras board — Órdenes area (default)

- [x] 3.1 Board chrome in `PurchasingView.vue`: header (`.eyebrow` "Compras"), pill area tabs
  Órdenes / Solicitudes / Proveedores, branch-scoped load on activation; reuse/extend
  `ProcurementPanel.vue` for data
- [x] 3.2 Stats row (4 KPI `.card .animate-docket`): total órdenes, en curso/parcial, recibidas,
  total por pagar — computed from the loaded list
- [x] 3.3 Toolbar (search proveedor/nº orden, supplier `Select`, status `Select`, sort, list/cards
  toggle) + dismissable filter chips with clear-all; filters combine (AND), apply live
- [x] 3.4 Sortable table + card view: supplier, fecha, total, receipt-progress bar, status +
  payment pills, kebab menu (Ver ítems / Recibir / Registrar pago); rows tinted by state
- [x] 3.5 Order detail drawer (`Teleport`, right aside, Esc/scrim close) with Detalles / Ítems /
  Pagos tabs — items show ordered vs received; Pagos shows the payment timeline + outstanding

## 4. Actions and secondary areas

- [x] 4.1 "Recibir mercancía" modal: per-item counted quantities + employee `Select` → receive
  action; friendly error on over-receive (409/422); gated `purchasing.manage`; write-through reload
- [x] 4.2 "Registrar pago" modal: amount + method + employee → registerPayment; friendly error when
  no open cash session; gated `purchasing.manage`
- [x] 4.3 Solicitudes area: request list bucketed by status, crear solicitud, approve/reject
  (gated `purchasing.approve`), crear orden desde aprobada; partial-success copy on the multi-write
  flow
- [x] 4.4 Proveedores area: embed existing `SuppliersPanel.vue`/`SupplierDetail.vue` as the tab, no
  behavior change; gates `purchasing.manage` preserved
- [x] 4.5 Alerts affordance (saldo pendiente + parcialmente recibidas) with Registrar pago / Recibir
  quick actions; CSV export of the current filtered order list (client-side)

## 5. Swap and cleanup

- [x] 5.1 Verify end-to-end against seeded data: orders show correct progress bars and stats;
  receive updates progress + stock; payment reduces outstanding; approve→crear orden works and is
  gated; read-only without `purchasing.manage`/`purchasing.approve`; filters/chips/sort/export;
  Proveedores tab parity
- [x] 5.2 Point the Compras nav + `/purchasing` at the board; redirect `/procurement` → `/purchasing`;
  delete `ProcurementView.vue` and `ProcurementPanel.vue` (and any now-dead wrappers)
- [x] 5.3 Frontend quality gates: `pnpm type-check`, `pnpm lint`, `pnpm test:unit`, `pnpm build`
