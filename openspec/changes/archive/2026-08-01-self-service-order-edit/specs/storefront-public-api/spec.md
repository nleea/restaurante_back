## ADDED Requirements

### Requirement: Per-order edit token

The public API SHALL mint an edit token bound to a single order when that order is created, and
SHALL expose it to the caller that created the order so it can be delivered as a link. The token
SHALL have its own lifetime, independent of the conversation's store token.

The store token — which identifies a **contact** — SHALL NOT authorise an edit. Reusing it would
make a forwarded link grant access to every open order of that customer.

#### Scenario: Creating an order yields its edit link

- **WHEN** an order is created through the public API
- **THEN** the response carries a token that addresses that order and no other

#### Scenario: A contact token cannot edit

- **WHEN** a conversation store token is presented to an edit endpoint
- **THEN** the request is refused

### Requirement: Public order read by token

The public API SHALL expose the order behind an edit token: its lines with their products,
quantities, addons, notes and per-item editability, plus the order total and the amount still
owed.

It SHALL NOT expose anything that does not belong to that order, and SHALL NOT require any other
identification from the customer.

#### Scenario: The customer sees their own order

- **WHEN** a valid edit token is presented
- **THEN** the order's lines, totals and what can still be changed are returned

#### Scenario: Nothing else is reachable

- **WHEN** the response is inspected
- **THEN** it contains no data about other orders, other customers or other branches

### Requirement: Public order edit by token

The public API SHALL accept edits to the order behind an edit token, restricted to: adding an
item, increasing a quantity, attaching an addon, editing a note, and swapping a line's product.
It SHALL refuse removals, decreases and cancellation.

Prices SHALL be resolved from the branch's active catalogue. A price supplied by the caller
SHALL be ignored.

Every rule of the `self-service-order-edit` capability — the never-decreasing total, the per-item
and per-order windows, and the paid-line restriction — SHALL be enforced by this endpoint
regardless of what the client sent.

#### Scenario: The client cannot set a price

- **WHEN** an edit request includes a unit price
- **THEN** the value is ignored and the catalogue price is used

#### Scenario: A refused edit changes nothing

- **WHEN** an edit violates any rule of the capability
- **THEN** the order is left exactly as it was and the reason is reported

#### Scenario: The response carries what the customer must be told

- **WHEN** an edit is accepted
- **THEN** the response includes the new total and the amount still owed
