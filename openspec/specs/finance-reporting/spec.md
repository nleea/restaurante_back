# finance-reporting

## Purpose

Read-only, tenant/branch-scoped finance reporting: revenue summaries and channel
breakdowns, payment-method mix, daily income-vs-expenses and cumulative cash-flow
series, top products, per-cash-session Reporte Z (with arqueo), cost-free manager
KPIs, and estimated taxes. Aggregates existing orders, payments, cash sessions and
the expense ledger without ever mutating them; cost-dependent KPIs are delivered
once the `product-costing` capability exists.
## Requirements
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

The system SHALL compute a daily income-vs-expenses series (income from orders, expenses from the expense ledger, grouped by day) for the revenue charts. The complete, cash-basis money movement (including manual cash movements and supplier payments) is provided by the dedicated cash-flow aggregation, not by this accrual income-vs-expenses series.

#### Scenario: Daily income vs expenses

- **WHEN** the daily series is requested for a range
- **THEN** each day returns its income and expense totals

### Requirement: Cash-flow aggregation (money-in / money-out)

The system SHALL expose a read-only, cash-basis, method-agnostic cash-flow aggregation for a branch and date range at `GET /reports/cash-flow`, gated by `finance.read` and scoped by `tenant_id` and `branch_id`. Every flow SHALL be read from exactly one source so no peso is double-counted: sales inflow from `order_payments` (branch-scoped, all methods); supplier outflow from `purchase_payments` joined to `purchase_orders` for the branch (all methods); operating outflow from `expenses`; and the manual retiros/ingresos and cash credit abonos from `cash_movements`. Because `cash_movements` mirrors sales and supplier payments, the aggregation SHALL exclude `sale` movements (read from `order_payments`) and `purchase_payment` movements (read from `purchase_payments`); it SHALL include `credit_payment` inflow movements and all remaining manual `in`/`out` movements. Customer credit payments are read from their branch-scoped cash movement (source table is tenant-scoped); non-cash abonos are out of scope. The response SHALL include total inflows, total outflows, net flow (inflows − outflows), a per-day series, and a category breakdown, and SHALL NOT include an absolute cash balance.

#### Scenario: A paid purchase appears as an outflow

- **WHEN** a purchase order has a registered supplier payment within the range (any method)
- **THEN** its amount is included in cash-flow outflows under the purchases category

#### Scenario: Sales are counted once, not double-counted with the mirror ledger

- **WHEN** an order payment has both an `order_payments` row and a mirrored `cash_movements` row with `concept = sale`
- **THEN** the sale is counted exactly once (from `order_payments`), and the mirrored movement is excluded

#### Scenario: Manual retiros and ingresos are included

- **WHEN** the cash drawer has manual `in`/`out` movements (concepts other than `sale`, `credit_payment`, `purchase_payment`) in the range
- **THEN** those amounts are included as inflows/outflows respectively

#### Scenario: Net flow and scoping

- **WHEN** the report is requested for a branch and range
- **THEN** net flow equals total inflows minus total outflows, computed only from that tenant's and branch's rows within the range, with no absolute balance returned

### Requirement: Cash-flow cash-vs-other split

The cash-flow report SHALL separate the physical-cash portion (payment method `cash`) from other methods (card/Nequi/transfer), so the cash portion can be reconciled against the arqueo while the remainder is presented as funds in transit to bank/wallets.

#### Scenario: Split reported per direction

- **WHEN** inflows and outflows include both cash and non-cash methods
- **THEN** the response reports the cash-method subtotal separately from the other-methods subtotal for each direction

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

### Requirement: List closed sessions for a branch

The system SHALL provide a read that lists a branch's closed cash sessions, most recent first, so staff can pick a past shift to review.

#### Scenario: Closed sessions listed

- **WHEN** the closed-sessions list is requested for a branch
- **THEN** the branch's closed sessions are returned, most recent first

### Requirement: Per-session operational record

The system SHALL provide, for a given closed session, its operational record — the orders, deliveries, kitchen tickets and payments belonging to that session (`cash_session_id`) — as read-only history alongside the Reporte Z.

#### Scenario: Session record aggregated

- **WHEN** the operational record is requested for a closed session
- **THEN** it returns the orders, deliveries, tickets and payments stamped to that session

#### Scenario: Legacy rows excluded

- **WHEN** a session's record is built
- **THEN** orders/deliveries with no `cash_session_id` are not included

