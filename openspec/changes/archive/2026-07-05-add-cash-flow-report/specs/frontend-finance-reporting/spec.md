## ADDED Requirements

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
