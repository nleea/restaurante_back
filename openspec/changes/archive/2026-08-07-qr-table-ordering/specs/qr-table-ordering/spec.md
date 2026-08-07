## ADDED Requirements

### Requirement: A dining table carries a stable public code

Every dining table SHALL carry a `code`: a short, URL-safe string, unique within its branch,
generated when the table is created and never rotated afterwards.

The code is printed on a sticker fixed to the table. It is therefore NOT a secret and MUST NOT be
treated as one: a rotating code would require reprinting every sticker on every rotation, and a
business that fails to reprint in time cannot sell in its dining room at all. What actually gates a
table order is dynamic and lives elsewhere — an open cash session, open business hours, and the fact
that a table is a physical place where somebody has to pay before leaving.

The code SHALL be distinct from `number`. The number belongs to the business and changes when it
renumbers its floor; the code belongs to the sticker and never changes. Deriving one from the other
would invalidate printed paper the day the floor is renumbered.

Codes SHALL avoid visually ambiguous characters, because a customer who cannot scan will type what
they read.

#### Scenario: A code is minted with the table
- **WHEN** an authorized user creates a dining table
- **THEN** the table is persisted with a generated `code` unique within its branch, and the code is
  returned with the table

#### Scenario: The code survives renumbering
- **WHEN** an authorized user changes a table's `number`
- **THEN** its `code` is unchanged and the printed QR keeps resolving to that table

#### Scenario: Existing tables get codes
- **WHEN** the change is deployed against a branch that already has tables
- **THEN** every existing table carries a code and no two tables of a branch share one

### Requirement: A table order names its diner without registering a customer

An order SHALL be able to carry `diner_name`: the first name the diner gives before building their
cart. It SHALL NOT create or reference a `customers` record, and no phone number SHALL be required
to place a table order.

The name exists because the money later needs it. When a cashier splits a table's bill they must be
able to point at Luis's order; three anonymous orders on table 5 are distinguishable only by
timestamp. Numbering them instead (`M5-1`, `M5-2`) moves the problem to the customer, who would have
to remember they were number 2.

A first name is not a customer. Writing it into `customers` would pollute the records that back
credit (fiado), purchase history and customer stats with people who only wanted lunch.

`diner_name` SHALL be optional: every order placed before this capability existed, and every order a
waiter opens, has none.

#### Scenario: The diner's name rides on the order
- **WHEN** a diner places a table order giving the name "Ana"
- **THEN** the created order carries `diner_name` "Ana" and no `customers` record is created or
  looked up

#### Scenario: No phone is demanded
- **WHEN** a diner places a table order
- **THEN** the order is accepted without a phone number and `customer_id` remains null

#### Scenario: Two diners with the same name are still distinguishable
- **WHEN** two orders on the same table both carry `diner_name` "Ana"
- **THEN** each is still identified by its own order label, which is what staff read aloud

### Requirement: An order records where it came from

An order SHALL carry `origin`, one of `staff`, `web` or `qr`, defaulting to `staff`.

A `dine_in` order opened by a waiter and one placed by scanning a table QR are otherwise identical —
same channel, same system employee — and three different consumers need to tell them apart: the
kitchen, to know that no human reviewed the order; the floor board, to render a table that is
serving itself; and reporting, to say how much the QR sold.

`origin` SHALL be a stored field, not inferred. Inferring it from "channel `dine_in` plus system
employee" breaks the day any other path attributes an order to the system employee.

#### Scenario: A QR order is marked
- **WHEN** an order is placed through a table QR
- **THEN** it is persisted with `origin` `qr`

#### Scenario: Staff orders keep the default
- **WHEN** an authorized employee opens an order from the floor
- **THEN** it is persisted with `origin` `staff`

#### Scenario: Pre-existing orders are staff orders
- **WHEN** orders created before this capability are read
- **THEN** their `origin` is `staff`

### Requirement: A table order reaches the kitchen when the diner confirms

Placing a table order SHALL route it to the kitchen immediately, in the same operation that creates
it. This is a deliberate exception to public order intake, which leaves a web order pending staff
confirmation.

The reason web orders wait is that a stranger placed them from a distance and the business wants a
human look before it spends ingredients. The person confirming a table order is sitting in the
dining room, in front of the food they will pay for. Confirming IS the commitment, and the review
that staff perform for a web order is performed here by the diner reading their own cart.

Adding to an existing table order through the diner's own link SHALL route what was added, exactly
as the existing self-service edit already does. Each confirmation is therefore a round, and rounds
are separate kitchen tickets because they are routed at different moments. No round counter is
stored.

A table order SHALL be created with no payment method, which the kitchen's payment gate already
treats as cash — money that arrives later. Table orders are paid on close.

#### Scenario: Confirming fires the order
- **WHEN** a diner confirms a table order with valid items
- **THEN** kitchen tickets are created for its items in the same operation, and the order is open
  and unpaid

#### Scenario: A later round fires on its own
- **WHEN** the same diner adds a dessert from their link and confirms again
- **THEN** only the added item is routed, as a separate ticket, and the already-cooking items are
  untouched

#### Scenario: What the kitchen started cannot be changed
- **WHEN** a diner tries to change a line whose station has already started it
- **THEN** the edit is refused with the reason shown, exactly as the existing self-service edit does

#### Scenario: No payment method blocks the stove
- **WHEN** a table order with no chosen payment method is routed
- **THEN** the kitchen payment gate allows it, because an order with no method counts as cash

### Requirement: A table is occupied by food, not by curiosity

Scanning a table's QR SHALL NOT change the table's status. A table SHALL become `occupied` when the
first order on it is confirmed.

A passer-by who scans out of curiosity would otherwise mark a table occupied with nobody sitting at
it, and the floor would withdraw it from service.

#### Scenario: Scanning changes nothing
- **WHEN** a table's QR is resolved
- **THEN** the table's status is unchanged

#### Scenario: The first confirmed order occupies the table
- **WHEN** the first order on a free table is confirmed
- **THEN** the table's status becomes `occupied`

#### Scenario: A second diner does not re-occupy
- **WHEN** a second order is confirmed on a table that is already `occupied`
- **THEN** the table's status is unchanged and both orders reference the same table
