## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Daily series and cash-flow

The system SHALL compute a daily income-vs-expenses series (income from orders, expenses from the expense ledger, grouped by day) for the revenue charts. The complete, cash-basis money movement (including manual cash movements and supplier payments) is provided by the dedicated cash-flow aggregation, not by this accrual income-vs-expenses series.

#### Scenario: Daily income vs expenses

- **WHEN** the daily series is requested for a range
- **THEN** each day returns its income and expense totals
