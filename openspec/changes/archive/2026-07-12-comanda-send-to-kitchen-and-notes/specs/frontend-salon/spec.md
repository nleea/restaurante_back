# frontend-salon (delta)

## MODIFIED Requirements

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
