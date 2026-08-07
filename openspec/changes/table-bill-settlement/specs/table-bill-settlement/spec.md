## ADDED Requirements

### Requirement: A table bill groups open orders of one table

The system SHALL allow authorized users to open a table bill over one or more `open` orders of the
same dining table in the same branch. Opening a bill for a table SHALL preselect **every** open
order on it; the caller MAY exclude members.

An order SHALL belong to at most one open bill at a time. Membership is a scalar column on the
order, so pointing at two bills is impossible by construction; claiming an order that another open
bill already holds SHALL be prevented atomically in the database — a conditional update that only
claims unclaimed orders, checking how many rows it changed — and not by a read-then-write in the
application. Two cashiers with the same table on screen is an ordinary situation, not an edge case.

A bill SHALL NOT freeze an amount when it opens. Its total is computed when it is charged, because a
diner can order coffee while the cashier is at the till.

A bill SHALL be dissolvable while `open`, releasing its members untouched.

#### Scenario: Open a bill for a whole table
- **WHEN** an authorized user opens a bill for a table with three open orders
- **THEN** a bill is created with all three as members and no amount frozen

#### Scenario: Open a bill for one diner
- **WHEN** an authorized user opens a bill over a single order of a table
- **THEN** a bill with that one member is created, and the table's other orders are untouched

#### Scenario: Reject mixing tables
- **WHEN** a bill is opened over orders belonging to different tables
- **THEN** the system responds with a validation error and creates no bill

#### Scenario: Reject an order already on an open bill
- **WHEN** an order that is already a member of an open bill is added to another
- **THEN** the system responds with a conflict error

#### Scenario: Reject a non-open order
- **WHEN** a bill is opened over an order that is `closed` or `cancelled`
- **THEN** the system responds with a validation error

#### Scenario: Dissolve a bill
- **WHEN** an authorized user dissolves an open bill
- **THEN** its member orders are released, still `open`, with no payments recorded

### Requirement: Charging a bill cascades into real per-order payments

Registering a payment on a table bill SHALL allocate it across the bill's member orders in
ascending order of the orders' creation time (`id` breaking ties), filling each order to its own
total before moving to the next, and SHALL write a real `order_payment` and its cash movement for
each allocation, through the same path a single-order charge already takes.

Allocation is waterfall, not pro-rata. Pro-rata would split every payment into fragments nobody
asked for, produce rounding cents, and make refunds unreadable ("return $17,333 of the card
payment"). Waterfall produces amounts a human recognises, and an order paid partly by card and
partly in cash is a case the system already handles.

`order_payments` SHALL remain the only source of truth for whether an order is paid. The bill
asserts nothing about money; it only groups.

A bill MAY be charged with several payments of different methods until it is covered.

Excess SHALL be treated as change against the last covered order, which is the existing overpayment
rule.

Charging SHALL require an open cash session, which is the existing rule for any payment.

#### Scenario: One payment covers the table
- **WHEN** a bill over three orders totalling 120,000 is charged 120,000 in cash
- **THEN** each member order receives a payment equal to its own total, and each has a matching cash
  movement in the open session

#### Scenario: Two methods split across the waterfall
- **WHEN** the same bill is charged 80,000 by card and then 40,000 in cash
- **THEN** the allocation fills orders in order, and the order that straddles the boundary carries
  two payments of different methods summing to its total

#### Scenario: Overpayment is change
- **WHEN** a bill is charged more than its total
- **THEN** the excess is treated as change and no error is raised

#### Scenario: A partial charge leaves the bill open
- **WHEN** a bill is charged less than its total
- **THEN** the covered orders hold their payments, the bill remains `open`, and nothing is closed

#### Scenario: No open cash session refuses the charge
- **WHEN** a bill is charged while its branch has no open cash session
- **THEN** the charge is refused and no payment or movement is written

### Requirement: A covered bill closes its orders in one transaction

When a bill's allocations cover every member order, the system SHALL close all of them and mark the
bill `settled`, in the same transaction as the allocation.

Allocation and cascading close SHALL be atomic. A failure halfway that leaves one diner closed and
another charged but open is the worst possible outcome of this capability, and the system MUST NOT
be able to reach it.

Each member order SHALL pass the ordinary close rule on its own merits: its payments cover its
total. The close path is not relaxed, bypassed or given an exception for bills — the rule that
kept unpaid closes from making sales disappear from the till stays exactly as it is.

Closing the last open order on the table SHALL free the table, which is the existing conditional
rule.

#### Scenario: A covered bill settles everything
- **WHEN** a bill's payments cover all its members
- **THEN** every member order is `closed` with `closed_at` set, and the bill is `settled`

#### Scenario: The table is freed by the cascade
- **WHEN** the settled bill held the table's last open orders
- **THEN** the table becomes `free`

#### Scenario: A diner still eating keeps the table
- **WHEN** a bill settles while another order on that table is still open
- **THEN** the table remains `occupied`

#### Scenario: Failure leaves nothing half-done
- **WHEN** any part of the allocation or the cascading close fails
- **THEN** no payment, no cash movement and no close survives the operation

#### Scenario: Inventory is deducted once per order
- **WHEN** a bill settles
- **THEN** each member order deducts its ingredients exactly once, by the existing idempotent path

### Requirement: A bill is charged in full or its members leave it

A table bill SHALL NOT be settled with an uncovered remainder. Credit (fiado) SHALL NOT be applied
at bill level.

A diner who is going on credit is removed from the bill and closed through the existing single-order
path, which already assigns a customer and records the credit. Allowing credit inside the group
would force the allocation to know which members may end uncovered and the cascading close to apply
two different rules depending on the member; removing them costs one gesture and leaves both rules
where they belong.

#### Scenario: Reject settling an uncovered bill
- **WHEN** a settle is attempted while some member order is not covered
- **THEN** the system responds with a validation error naming the missing amount, and closes nothing

#### Scenario: A credit diner is settled separately
- **WHEN** a member is removed from the bill and closed on credit through the single-order path
- **THEN** that order closes on credit and the remaining bill settles on its own

### Requirement: The table receipt is a document that says what it is

The system SHALL record a receipt print for a table bill. `receipt_prints` SHALL accept either an
`order_id` or a `table_bill_id`, exactly one of the two, and SHALL keep marking whether a print is
the first or a reprint, attributed to an employee.

The receipt SHALL carry the business name, tax id, address and branch, the table, the date and time,
the cashier, each member order grouped under its diner name with its order label and lines, the
totals, and the payment methods used.

The receipt SHALL state, in words, that it is not an electronic invoice. In Colombia a slip bearing
a business name, a NIT and a total looks very much like a fiscal document and is not one; a paper
that resembles an invoice without being one is worse than a paper that says what it is. When
electronic invoicing arrives, that sentence is what gets replaced.

#### Scenario: Print a table receipt
- **WHEN** an authorized user records a print for a settled bill
- **THEN** a receipt-print record is created against the bill with `is_reprint` false

#### Scenario: Reprint the table receipt
- **WHEN** a print is recorded for a bill that already has one
- **THEN** a record is created with `is_reprint` true

#### Scenario: Order and bill prints stay distinct
- **WHEN** a bill's receipt is printed
- **THEN** no receipt-print record is created against its member orders, so a later single-order
  print is still a first print

#### Scenario: Reject a print referencing both or neither
- **WHEN** a receipt print is recorded with both an order and a bill, or with neither
- **THEN** the system rejects it

### Requirement: RBAC protection of table bill endpoints

Opening, dissolving, charging and printing a table bill SHALL require the same permissions that
govern charging and closing an order today. No new permission is introduced: settling a table is the
same authority as settling a comanda, exercised over several at once.

#### Scenario: An unauthorized user is refused
- **WHEN** a user without the permission to charge orders attempts to charge a bill
- **THEN** the system responds 403 Forbidden and writes nothing
