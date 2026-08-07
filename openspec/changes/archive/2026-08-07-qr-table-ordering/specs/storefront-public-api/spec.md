## ADDED Requirements

### Requirement: Public table resolution by branch and table code

`GET /storefront/{branch_code}/tables/{table_code}` SHALL resolve a dining table without
authentication, scoped to the subdomain tenant, and return the table's number, its branch, and
whether the business can take orders right now (open cash session and open business hours).

The branch and the table both come from the URL, never from a payload — the same rule the public
menu already defends. A table travelling in the request body would let somebody order to table 5
while looking at another branch's menu; in the path, the order cannot contradict the menu that was
seen.

Resolution SHALL NOT change the table's status.

An unknown or inactive table code, or a table that does not belong to the addressed branch, SHALL be
rejected with 404 Not Found. It MUST NOT fall back to any other table, for the same reason branch
resolution never falls back to the primary branch.

#### Scenario: Resolve a table from its QR
- **WHEN** an unauthenticated request resolves an active table code under its branch code
- **THEN** the table's number and branch are returned, together with whether orders can be taken now

#### Scenario: Reject a table code from another branch
- **WHEN** a table code that belongs to a different branch is resolved under this branch code
- **THEN** the system responds 404 Not Found and no table is returned

#### Scenario: Reject an unknown or inactive table
- **WHEN** an unknown or deactivated table code is resolved
- **THEN** the system responds 404 Not Found

#### Scenario: Resolving is read-only
- **WHEN** a table is resolved
- **THEN** its status is unchanged

### Requirement: Public table order intake fires to the kitchen

`POST /storefront/{branch_code}/tables/{table_code}/orders` SHALL create a real order without
authentication, scoped to the subdomain tenant. It SHALL require a diner name and at least one line;
it SHALL NOT require a phone number and SHALL NOT create or reuse a `customers` record.

It SHALL open the order on the tenant's system employee with channel `dine_in`, `origin` `qr`, the
resolved `dining_table_id`, the given `diner_name`, and no payment method — table orders are paid on
close. It SHALL add each line with its addons and kitchen note (ingredient removals folded into the
note, composed by the server), mint the order's edit token, and **route the order to the kitchen in
the same operation**.

Routing is the deliberate difference from web intake, which leaves an order pending staff
confirmation. A web order is placed by a stranger at a distance and deserves a human look before
ingredients are spent; a table order is confirmed by someone sitting in the dining room in front of
the food they will pay for. The diner performs the review that staff perform for a web order.

No `order_payments` row is created at intake: money is received when the bill is settled.

#### Scenario: A confirmed table order is created and fired
- **WHEN** an unauthenticated diner confirms a valid cart on a resolved table
- **THEN** a `dine_in` order is created with that table, diner name and `origin` `qr`
- **AND** kitchen tickets exist for its items in the same operation
- **AND** the order is open, unpaid, and carries an edit token

#### Scenario: No phone, no customer record
- **WHEN** a table order is placed
- **THEN** it is accepted with no phone number and its `customer_id` is null

#### Scenario: Confirming again adds a round
- **WHEN** the diner adds items through their edit token and confirms
- **THEN** only the added items are routed, as separate tickets

#### Scenario: Empty or invalid cart is rejected
- **WHEN** a submission has no line items or references a non-sellable/unknown product
- **THEN** the system responds with a validation error and creates no order and no ticket

#### Scenario: Removals ride in the kitchen note
- **WHEN** a cart line excludes ingredients (e.g. "sin cebolla")
- **THEN** the created order item's kitchen note conveys those removals so the kitchen sees them

### Requirement: Table intake refuses when the business cannot serve

Table order intake SHALL be refused when the branch has no open cash session, with the same
`cash_closed` conflict the existing public intake returns, and the refusal SHALL be phrased for a
customer rather than as a system error.

Table resolution SHALL report that state **before** the diner builds a cart. A diner who assembles
an order and is rejected at the last step has been made to waste their time by a condition the
system knew from the first request.

#### Scenario: Closed caja is told up front
- **WHEN** a table is resolved while its branch has no open cash session
- **THEN** the response says orders cannot be taken now, before any menu interaction

#### Scenario: Closed caja still refuses intake
- **WHEN** a table order is submitted while the branch has no open cash session
- **THEN** the system refuses it and creates no order
