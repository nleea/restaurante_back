## MODIFIED Requirements

### Requirement: Create a delivery order from the Salón

The Salón SHALL let a user with `orders.create` start a delivery order that opens a real order with
`channel: 'delivery'` (no table) with the resolved employee.

When the channel is Domicilio, the new-order dialog SHALL capture the customer's **address** — the
moment it is being heard — and, once the order is open, SHALL create the order's delivery record with
that address. Address capture SHALL require `delivery.address`; a user without it SHALL still be able
to open a delivery order, leaving the address to be captured later (from the comanda or from
`/dispatch`).

The pin SHALL NOT be picked here: creating the delivery record with an address alone lets the backend
geocode an approximate pin. Map picking and pin correction remain the responsibility of the
Delivery/Dispatch modules, as does driver assignment and tracking.

Opening the order and creating its delivery record are two calls. If the order opens but the delivery
record fails, the order SHALL NOT be discarded and the Salón SHALL still open its ticket: the order
is genuinely open, and the comanda's Domicilio card then shows the address as missing, which is both
the signal and the recovery. If the **order itself** fails to open, the dialog SHALL stay open with
the reason.

#### Scenario: Open a delivery order with its address

- **WHEN** a user with `orders.create` and `delivery.address` starts a new delivery order and gives an address
- **THEN** a `channel: 'delivery'` order is opened with no table and the resolved employee, its delivery record is created with that address, and its ticket opens

#### Scenario: Open a delivery order without the address permission

- **WHEN** a user with `orders.create` but without `delivery.address` starts a new delivery order
- **THEN** the dialog does not ask for an address, the order opens, and its ticket opens

#### Scenario: The address is required by the dialog

- **WHEN** a user with `delivery.address` picks the Domicilio channel and submits with an empty address
- **THEN** the dialog blocks the submit and asks for the address

#### Scenario: The order survives a failed delivery record

- **WHEN** the order opens but creating its delivery record fails
- **THEN** the ticket still opens with the order intact, and the comanda's Domicilio card shows the address as missing so it can be captured there

## ADDED Requirements

### Requirement: Capture and correct the delivery address from the comanda

For an order with `channel: 'delivery'`, the comanda (`/floor/order/:id`) SHALL show a Domicilio card
carrying the delivery address, so the address can be written when the order arrived without one and
corrected for as long as the order is open.

The card SHALL require `delivery.address` to write; without it the address SHALL be read-only, and
without `delivery.address` and `delivery.read` the card SHALL be hidden.

An order with no delivery record yet SHALL be presented as a "sin dirección" state inviting capture,
not as an error — that is the normal state of every delivery order opened before this change and of
any order whose address capture failed. Writing the address from this state SHALL create the delivery
record; writing it afterwards SHALL update the existing one.

The card SHALL NOT offer map picking or pin editing; those stay in `/dispatch`.

#### Scenario: A delivery order without an address invites capture

- **WHEN** a user with `delivery.address` opens the comanda of a `channel: 'delivery'` order that has no delivery record
- **THEN** the Domicilio card shows a "sin dirección" state offering to add it

#### Scenario: Capturing the address creates the delivery record

- **WHEN** the user writes an address on an order that has no delivery record
- **THEN** the order's delivery record is created with that address and the card shows it

#### Scenario: Correcting the address updates the record

- **WHEN** the user edits the address of an order that already has a delivery record
- **THEN** the delivery record is updated and the card shows the new address

#### Scenario: The card is absent for non-delivery orders

- **WHEN** the comanda shows an order whose channel is not `delivery`
- **THEN** no Domicilio card is shown

#### Scenario: Read-only without the write permission

- **WHEN** a user holding `delivery.read` but not `delivery.address` opens a delivery order's comanda
- **THEN** the address is shown but cannot be edited
