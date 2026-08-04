# frontend-salon (delta)

## MODIFIED Requirements

### Requirement: Table action panel drives the real order lifecycle

Taking or opening an order from the Salón SHALL navigate to a routed order detail at
`/floor/order/:id` — the redesigned Comanda for that order — instead of opening a
ticket dialog in place. The Salón stays the home surface (mesas grid + a "Para llevar y
domicilios" strip); the detail MUST be deep-linkable and browser-back MUST return to
the grid. The legacy standalone `/comanda` route SHALL redirect to `/floor`.

#### Scenario: Take an order for a free table

- **WHEN** an authorized user takes an order for a table from the Salón
- **THEN** the order is opened and the app navigates to `/floor/order/:id` showing the Comanda

#### Scenario: Open the existing order of an occupied table

- **WHEN** the user opens the order of an occupied table (or a takeaway/delivery order)
- **THEN** the app navigates to that order's `/floor/order/:id` detail

#### Scenario: Back returns to the grid

- **WHEN** the user leaves the order detail (back affordance or browser back)
- **THEN** the Salón grid is shown again

#### Scenario: Deep-link to a closed or missing order

- **WHEN** the user opens `/floor/order/:id` for an order that is closed or not found
- **THEN** they are redirected to `/floor` with a brief explanation

### Requirement: Ticket editing uses real menu variants and server totals

Order editing SHALL happen in the routed Comanda: a tap-to-add menu field (search + a
mono category rail + product tiles) writes items through the real orders API, and only
orderable products are shown (an active-branch price and at least one active variant).
Multi-variant products SHALL be picked via an on-tile popover, not a separate dropdown.
Because new items auto-route to the kitchen, each added line SHALL show an "en cocina"
state rather than a pending batch-send; there is no "Enviar a cocina" button.

#### Scenario: Add an item by tapping a tile

- **WHEN** the user taps an orderable product tile (choosing a variant when there is more than one)
- **THEN** the item is added to the order via the API and appears on the live dupe with an "en cocina" state

#### Scenario: Only orderable products are offered

- **WHEN** a product lacks an active-branch price or an active variant
- **THEN** it is not offered in the menu field

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
