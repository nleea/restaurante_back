# frontend-orders

## Purpose

The Comandas screen — the frontend client for the backend `/orders` API, scoped to the active
branch. It lets an authorized order-taker manage dining tables and run the order lifecycle:
open → add/edit/remove items (priced from the product's active-branch price plus the chosen
variant's `extra_price`) → set discount → close or cancel. The operating employee is resolved
via `GET /staff/employees/me`; item labels and prices are resolved client-side from the menu;
order totals are always the server's recomputation. The screen is reached only with `orders.read`,
and mutating controls are gated by their backend permissions (`orders.create`/`update`/`cancel`);
this gating is UX — the backend enforces authorization independently. Payments/cobro, receipts,
per-item cancellation, addons, and the KDS are out of scope for this first slice.

## Requirements

### Requirement: Resolve the operating employee

Before opening, cancelling, or otherwise acting as an employee, the screen SHALL resolve the current user's employee via `GET /staff/employees/me` and use its id for the operation. When the current user is not linked to an employee, the screen SHALL disable order-opening and explain that the account is not linked to an employee.

#### Scenario: Employee resolved on load

- **WHEN** an order-taker opens the comandas screen
- **THEN** the screen resolves their employee and enables opening orders

#### Scenario: Non-employee user is informed

- **WHEN** the current user is not linked to an employee
- **THEN** order-opening is disabled with a clear message

### Requirement: Manage dining tables for the active branch

The screen SHALL list the active branch's dining tables with their number, capacity, and status (`free` / `occupied`), and — gated by `orders.create` — let the user add a table (number + capacity).

#### Scenario: List tables

- **WHEN** the tables view loads for the active branch
- **THEN** each table shows its number, capacity, and status

#### Scenario: Create a table

- **WHEN** a user with `orders.create` adds a table with a number and capacity
- **THEN** the table is created and appears in the list

### Requirement: Open an order

The screen SHALL let an authorized user (`orders.create`) open an order for the active branch, choosing a channel (`dine_in`, `takeaway`, `delivery`) and, for `dine_in`, an available table. The order SHALL be opened with the resolved employee. On success the new order's ticket SHALL be shown.

#### Scenario: Open a dine-in order on a table

- **WHEN** the user opens a `dine_in` order and selects a free table
- **THEN** the order is created against the active branch, table, and resolved employee, and its ticket opens

#### Scenario: Open a takeaway order

- **WHEN** the user opens a `takeaway` order
- **THEN** the order is created with no table and its ticket opens

### Requirement: Build the ticket (items)

For a selected order, the screen SHALL show its items and the server-computed totals (subtotal, discount, total). It SHALL let an authorized user add an item by picking a product and one of its active sellable variants and a quantity — computing `unit_price` as the product's active-branch price plus the variant's `extra_price` and sending it — and edit an item's quantity (`orders.update`) or remove an item (`orders.update`). Items SHALL be labeled by product and variant name, not raw ids. After each change the displayed totals SHALL reflect the server's recomputation.

#### Scenario: Add an item priced from product + variant

- **WHEN** the user adds a product's variant with a quantity
- **THEN** the item is created with `unit_price = branch price + variant extra_price`, appears labeled by product/variant, and the order totals update

#### Scenario: Change an item quantity

- **WHEN** the user changes an item's quantity
- **THEN** the item's line subtotal and the order totals update

#### Scenario: Remove an item

- **WHEN** the user removes an item
- **THEN** the item disappears and the order totals update

### Requirement: Discount, close, and cancel an order

The screen SHALL let an authorized user set the order's discount (`orders.update`, bounded by the server to the subtotal), close the order (`orders.update`), and cancel the order with a reason (`orders.cancel`) using the resolved employee. Closing or cancelling a dine-in order frees its table.

#### Scenario: Set a discount

- **WHEN** the user sets a discount on an open order
- **THEN** the order total reflects `subtotal − discount` as recomputed by the server

#### Scenario: Close an order

- **WHEN** the user closes an open order
- **THEN** the order is marked closed and its table (if any) is freed

#### Scenario: Cancel an order

- **WHEN** the user cancels an open order with a reason
- **THEN** the order is marked cancelled (recording the resolved employee) and its table (if any) is freed
