# frontend-salon

## Purpose

The Salón floor screen — the frontend client for the backend `/orders` API, scoped to the active
branch. It replaces the standalone "Comandas" screen with a live floor grid: the active branch's
dining tables render as docket cards whose free/occupied state and totals come from the backend, and
selecting a table drives the real order lifecycle (open → edit ticket → discount → settle → close or
cancel). The operating employee is resolved via `GET /staff/employees/me`; item labels and prices are
resolved client-side from the menu; order totals are always the server's recomputation. The screen is
reached at `/floor` only with `orders.read` (legacy `/orders` redirects there), and mutating controls
are gated by their backend permissions (`orders.create`/`update`/`cancel`/`pay`); this gating is UX —
the backend enforces authorization independently.
## Requirements
### Requirement: Salón route is permission-gated

The system SHALL expose a `/floor` route that requires authentication and the `orders.read`
permission, and SHALL surface a single "Salón" navigation entry (in the "Servicio" group) only when
the user holds `orders.read`. The legacy `/orders` path SHALL redirect to `/floor`. Mutating controls
SHALL be gated by their backend permissions (`orders.create` for opening orders / adding items /
creating tables, `orders.update` for quantity / discount / close, `orders.cancel` for cancellation,
`orders.pay` for payments). This gating is UX; the backend enforces authorization independently.

#### Scenario: Authorized user reaches the Salón

- **WHEN** an authenticated user with `orders.read` navigates to `/floor`
- **THEN** the Salón renders and the "Salón" nav entry is visible

#### Scenario: Unauthorized user is blocked

- **WHEN** an authenticated user without `orders.read` navigates to `/floor`
- **THEN** the router redirects to the Forbidden view and the "Salón" nav entry is hidden

#### Scenario: Legacy orders path redirects

- **WHEN** a user navigates to `/orders`
- **THEN** the router redirects to `/floor`

### Requirement: Live floor grid backed by real tables and orders

The Salón SHALL render the active branch's dining tables as a responsive grid of docket cards,
loading tables and open orders from the `orders` store for the active branch, and SHALL re-scope
when the active branch changes. Each card SHALL show the table number and capacity and SHALL derive
its state from the backend: a table is **occupied when it has an open order** and **free**
otherwise. An occupied card SHALL show the open order's server-computed total; a free card SHALL
show a free affordance. The card status color SHALL follow the "El Pase" semantic palette
(free → success, occupied → ember).

#### Scenario: Tables render for the active branch

- **WHEN** the Salón loads with an active branch
- **THEN** every active table appears as a card showing its number, capacity, and free/occupied state

#### Scenario: Occupied table shows its order total

- **WHEN** a table has an open order
- **THEN** its card is styled occupied and shows the order's server-computed total

#### Scenario: Re-scope on branch change

- **WHEN** the active branch changes
- **THEN** the grid reloads tables and open orders for the new branch and clears any selection

### Requirement: Table action panel drives the real order lifecycle

Taking or opening an order from the Salón SHALL navigate to the routed order detail at
`/floor/order/:id`. The table action panel SHALL also offer a **Liberar mesa** action for
an occupied table that cancels its order and returns the table to libre, offering one-tap
reasons ("Cliente se fue", "Mesa equivocada") so no free-text is required. The Salón stays
the home surface (mesas grid + "Para llevar y domicilios").

#### Scenario: Release a table when nobody ordered

- **WHEN** the user selects an occupied table and chooses "Liberar mesa" with a one-tap reason
- **THEN** the order is cancelled and the table returns to libre

#### Scenario: Take an order navigates to the detail

- **WHEN** an authorized user takes an order for a table
- **THEN** the order opens and the app navigates to `/floor/order/:id`

### Requirement: Ticket editing uses real menu variants and server totals

Order editing SHALL happen in the routed Comanda, and items SHALL NOT reach the kitchen on
add. When adding a product the user MAY attach a free-text **kitchen note** ("sin
lechuga"); the note is shown on the dupe line and travels to the KDS. Each line SHALL show
its kitchen state — **PENDIENTE** (not yet sent) or **EN COCINA** (`sent`) — and an
**Enviar a cocina** action SHALL route the pending lines (repeatable per round). Adding
items and sending are distinct steps.

#### Scenario: Add an item with a note, still pending

- **WHEN** the user taps a product and adds a kitchen note
- **THEN** the line appears with the note and a PENDIENTE state, and no ticket is created yet

#### Scenario: Send to the kitchen

- **WHEN** the user presses "Enviar a cocina" with pending lines
- **THEN** those lines are routed and flip to EN COCINA

#### Scenario: Send a later round

- **WHEN** more items are added after a first send and the user sends again
- **THEN** only the new pending lines are routed

### Requirement: Register a table from the Salón

The Salón SHALL let a user with `orders.create` register a new dining table with a number
(pre-filled with the next available number, editable) and a capacity, via `POST /orders/tables` for
the active branch, and the new table SHALL appear in the grid.

#### Scenario: Create a table

- **WHEN** a user with `orders.create` saves a new table with a number and capacity
- **THEN** the table is created for the active branch and appears in the grid as free

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

### Requirement: Settle and close an order from the Salón

Settling and closing SHALL happen in the Comanda's cobro sheet, which absorbs what the
old ticket did: register split payments per method, edit the discount, show paid /
saldo / vuelto, close a settled order, and cancel with a reason. When a balance remains,
the user MAY assign an **existing** registered customer to the order and then "Fiar y
cerrar"; the customer is chosen from the customers directory (no inline create — a
"Crear cliente" affordance routes to the Clientes view). Closing with no payment and no
customer is blocked with guidance.

#### Scenario: Close a settled order

- **WHEN** the order is fully paid (or overpaid) and the user closes it
- **THEN** the order closes; any overpayment is shown as vuelto

#### Scenario: Fiar the remainder to an existing customer

- **WHEN** a balance remains and the user picks an existing customer and chooses "Fiar y cerrar"
- **THEN** the customer is assigned to the order, the order closes, and the remainder becomes that customer's credit

#### Scenario: Close blocked without payment or customer

- **WHEN** a balance remains and no customer is assigned
- **THEN** closing is blocked and the UI guides the user to charge the rest or assign a customer

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

