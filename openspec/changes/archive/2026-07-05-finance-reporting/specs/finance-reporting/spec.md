## ADDED Requirements

### Requirement: Read-only, scoped reporting endpoints

The system SHALL expose finance reporting as read-only aggregation endpoints requiring `finance.read`, scoped to the tenant, filtered by `branch_id` and a date range `[from, to]`, with optional `cashier_employee_id`. Only closed/paid orders SHALL count as revenue. No reporting endpoint SHALL write to any module.

#### Scenario: Scoped revenue read

- **WHEN** an authorized user requests a revenue summary for a branch and date range
- **THEN** the system returns totals computed only from that tenant's, that branch's closed orders within the range

#### Scenario: Reads never mutate

- **WHEN** any reporting endpoint is called
- **THEN** no order, payment, cash session, or expense record is created or modified

### Requirement: Revenue summary and channel breakdown

The system SHALL compute, for a period, total revenue, ticket count, average ticket, and revenue broken down by `channel`, from closed orders.

#### Scenario: Revenue by channel

- **WHEN** a revenue summary is requested
- **THEN** the response includes total revenue, ticket count, average ticket, and an amount + ticket count per channel that sum to the totals

### Requirement: Payment-method mix

The system SHALL compute revenue by payment `method` (amount and percentage) from `order_payments` in the period.

#### Scenario: Payment mix

- **WHEN** the payment-method breakdown is requested
- **THEN** each method returns its total amount and its share of the period's paid total

### Requirement: Daily series and cash-flow

The system SHALL compute a daily income-vs-expenses series (income from orders, expenses from the expense ledger, grouped by day) and a cumulative cash-flow series from cash sessions/movements, including the operational-minimum threshold and whether it was breached.

#### Scenario: Daily income vs expenses

- **WHEN** the daily series is requested for a range
- **THEN** each day returns its income and expense totals

#### Scenario: Cash-flow threshold breach

- **WHEN** the cumulative cash balance drops below the configured minimum on any day
- **THEN** the cash-flow response flags the breach

### Requirement: Top products

The system SHALL rank products by revenue over the period from `order_items`, returning units sold and revenue per product.

#### Scenario: Top products by revenue

- **WHEN** the top-products report is requested
- **THEN** products are returned ranked by revenue with their units sold and revenue amount

### Requirement: Reporte Z per cash session

The system SHALL expose a per-cash-session Z report that aggregates the session's orders and payments into ventas-por-canal, métodos-de-pago, descuentos/devoluciones, arqueo (opening, expected, counted, difference taken from the cash session; retiros from cash movements), estimated taxes, and an operative summary (average ticket, peak hour, top product, top server). The report SHALL identify the shift window from the session times and the cashier from the session's opener.

#### Scenario: Generate a session Z report

- **WHEN** an authorized user requests the Z report for a closed cash session
- **THEN** the system returns the session's sales by channel, payment mix, arqueo (expected/counted/difference), estimated taxes, and operative summary

#### Scenario: Arqueo comes from the session

- **WHEN** the Z report renders the arqueo
- **THEN** opening, expected, counted and difference match the `cash_sessions` record, not a recomputed value

### Requirement: Cost-free manager indicators

The system SHALL compute the manager KPIs that do not require cost (average ticket by channel, RevPASH, month-over-month growth, retention where derivable) and clearly separate them from cost-dependent KPIs (which are delivered once product costing exists).

#### Scenario: Revenue-side KPIs available without costing

- **WHEN** manager indicators are requested and product costing is not yet available
- **THEN** the cost-free KPIs are returned and cost-dependent KPIs (food/labor/prime cost, margin) are omitted or marked unavailable

### Requirement: Estimated taxes are labeled

The system SHALL derive IVA (19%), INC and Impoconsumo as estimates from net sales and mark them as estimates in the response, never as filed tax.

#### Scenario: Taxes flagged as estimates

- **WHEN** a report includes tax figures
- **THEN** those figures are flagged as estimated (derived), not tracked tax
