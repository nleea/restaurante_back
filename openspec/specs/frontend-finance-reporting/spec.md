# frontend-finance-reporting

## Purpose

The Finanzas UI wired to the real reporting API: all six tabs (Resumen, Ingresos,
Gastos, Rentabilidad, Reporte Z, Reportes) rendered from live data on the
consolidated `/finance` route, preserving the El Pase design. Includes the sticky
global filter bar, expense recording against the real ledger, the Reporte Z docket
from real cash sessions, and graceful degradation of cost-dependent views until the
`product-costing` capability is available.
## Requirements
### Requirement: Finanzas module on real data

The Finanzas module SHALL render all six tabs (Resumen, Ingresos, Gastos, Rentabilidad, Reporte Z, Reportes) from the reporting API instead of in-memory seed data, preserving the El Pase design (mono tabular money, the Reporte Z docket, the SVG charts). It SHALL live on the consolidated `/finance` route (with `/finance/z` redirecting), appear once in the sidebar, and be gated by `finance.read`.

#### Scenario: Tabs read real data

- **WHEN** an authorized user opens Finanzas for the active branch and period
- **THEN** each tab's figures and charts come from the reporting API for that scope

#### Scenario: Route consolidation

- **WHEN** a user navigates to `/finance/z`
- **THEN** they are redirected to the consolidated `/finance` module

### Requirement: Global filter bar

The module SHALL show a sticky filter bar (período, sucursal, turno, cajero) that, on change, recomputes every visible KPI and chart by refetching the reporting API with the new scope.

#### Scenario: Changing the period recomputes

- **WHEN** the user changes the período (or sucursal / turno / cajero)
- **THEN** all KPIs and charts in the active tab refetch and re-render for the new scope

### Requirement: Gastos on the real expense ledger

The Gastos tab SHALL read and record expenses through the existing finance expense API (categories, expenses, record-expense), gated so recording requires `finance.manage`.

#### Scenario: Record an expense

- **WHEN** a user with `finance.manage` registers an expense
- **THEN** it is persisted via the finance API and appears in the Gastos table and category totals

### Requirement: Reporte Z from real sessions

The Reporte Z tab SHALL list real cash sessions and render the docket for a selected closed session from the Z reporting endpoint; the "cerrar turno" arqueo flow SHALL close the session through the existing cash API.

#### Scenario: View a real Z report

- **WHEN** a user selects a closed cash session
- **THEN** the docket renders that session's real sales, payment mix, arqueo and estimated taxes

#### Scenario: Close a shift

- **WHEN** a user completes the arqueo count for an open session and confirms
- **THEN** the session is closed via the cash API and its Z report becomes available

### Requirement: Profitability degrades gracefully without costing

Until product costing is available, the Rentabilidad tab and cost-dependent report cards SHALL clearly indicate that margin/COGS figures are pending costing, rather than showing seed or zero values.

#### Scenario: Rentabilidad before costing

- **WHEN** the Rentabilidad tab loads and COGS is not yet available
- **THEN** revenue and operating-expense lines render from real data while COGS/margin lines show a "pendiente de costeo" state

#### Scenario: Estimated taxes labeled in the UI

- **WHEN** the UI shows tax figures in the Z report or P&L
- **THEN** they are visibly labeled as estimates

### Requirement: Cash-flow report on real money movement

The Finanzas module SHALL present cash flow from the real cash-flow API (money-in/money-out) instead of a proxy. The Resumen cash-flow chart SHALL be driven by the API's net-cash daily series, and the Reportes "Flujo de caja" card SHALL open a breakdown of inflows and outflows by category with the cash-vs-other split. All cash-flow views SHALL respond to the global período/sucursal filter and be gated by `finance.read`.

#### Scenario: Resumen cash-flow chart uses real data

- **WHEN** an authorized user views Resumen for the active branch and period
- **THEN** the cash-flow chart plots the net-cash daily series from the cash-flow API, not a `revenue − expenses` proxy

#### Scenario: Flujo de caja report breakdown

- **WHEN** the user opens the "Flujo de caja" report card in Reportes
- **THEN** it shows inflows and outflows grouped by category and the cash-vs-other split for the selected period

#### Scenario: A purchase payment is visible

- **WHEN** a supplier payment for a purchase falls in the selected period
- **THEN** it appears in the cash-flow outflows, so the money spent on insumos is no longer invisible in Finanzas

### Requirement: Registros por turno view

The Finanzas area SHALL provide a "Registros por turno" view that lists closed sessions and drills into a selected session's operational record (orders/deliveries/tickets/payments), reusing the Reporte Z per-session framing.

#### Scenario: Browse and open a session record

- **WHEN** the user opens "Registros por turno" and selects a closed session
- **THEN** the session's operational record is shown alongside its Reporte Z

#### Scenario: Empty history

- **WHEN** a branch has no closed sessions yet
- **THEN** the view shows an empty state rather than an error

