## ADDED Requirements

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

Selecting a table SHALL open an action panel whose options reflect the table's live state and the
user's permissions. For a free table it SHALL offer "Tomar comanda" (open a `dine_in` order on that
table with the resolved employee). For an occupied table it SHALL offer viewing/editing the ticket,
registering payment, and closing or cancelling the order. Opening a table that is already occupied
by another order SHALL surface an actionable conflict message.

#### Scenario: Open an order on a free table

- **WHEN** a user with `orders.create` chooses "Tomar comanda" on a free table
- **THEN** a `dine_in` order is opened against the active branch, that table, and the resolved employee, and its ticket opens

#### Scenario: Conflict opening an occupied table

- **WHEN** opening an order fails because the table is already occupied (409)
- **THEN** the panel shows a clear "la mesa ya está ocupada" message and no duplicate order is created

#### Scenario: Non-employee cannot open orders

- **WHEN** the current user is not linked to an employee
- **THEN** order-opening is disabled with a message that the account is not linked to an employee

### Requirement: Ticket editing uses real menu variants and server totals

The Salón SHALL edit an open order through the retained `OrderTicket` (reused, not reimplemented):
adding an item by picking a product and one of its active sellable variants and a quantity —
computing `unit_price` as the product's active-branch price plus the variant's `extra_price` — and
editing quantity or removing an item. Items SHALL be labeled by product and variant name, and the
displayed subtotal/discount/total SHALL always reflect the server's recomputation. There SHALL be no
client-side tax calculation.

#### Scenario: Add a variant-priced item

- **WHEN** the user adds a product's variant with a quantity
- **THEN** the item is created with `unit_price = branch price + variant extra_price`, labeled by product/variant, and the order totals update from the server

#### Scenario: Totals come from the server

- **WHEN** any item is added, changed, or removed
- **THEN** the displayed subtotal, discount, and total are the server's values, with no client-computed tax

### Requirement: Register a table from the Salón

The Salón SHALL let a user with `orders.create` register a new dining table with a number
(pre-filled with the next available number, editable) and a capacity, via `POST /orders/tables` for
the active branch, and the new table SHALL appear in the grid.

#### Scenario: Create a table

- **WHEN** a user with `orders.create` saves a new table with a number and capacity
- **THEN** the table is created for the active branch and appears in the grid as free

### Requirement: Create a delivery order from the Salón

The Salón SHALL let a user with `orders.create` start a delivery order that opens a real order with
`channel: 'delivery'` (no table) with the resolved employee. Detailed driver assignment and tracking
remain the responsibility of the Delivery/Dispatch modules; the Salón only creates the order and
opens its ticket.

#### Scenario: Open a delivery order

- **WHEN** the user starts a new delivery order
- **THEN** a `channel: 'delivery'` order is opened with no table and the resolved employee, and its ticket opens

### Requirement: Settle and close an order from the Salón

The Salón SHALL let an authorized user register payments against the open order (through the ticket's
payment flow), apply a discount, and close or cancel the order, after which the freed table SHALL
return to the free state in the grid. A close/payment attempted with no open cash session SHALL
surface the backend's actionable message rather than a generic error.

#### Scenario: Close a paid order frees the table

- **WHEN** an occupied table's order is closed
- **THEN** the order leaves the open set and the table returns to free in the grid

#### Scenario: No open cash session is explained

- **WHEN** a payment is attempted with no open cash session (409)
- **THEN** the ticket surfaces the "no hay caja abierta" guidance instead of a generic failure
