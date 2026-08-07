# frontend-purchasing-orders (delta)

## ADDED Requirements

### Requirement: Compras board layout

The Compras screen SHALL be a board whose spine is the branch's purchase orders, with areas
switched by pill tabs — **Órdenes** (the orders table/cards), **Solicitudes** (requests) and
**Proveedores** (supplier management) — and a slide-in detail drawer for the selected order with
**Detalles**, **Ítems** and **Pagos** tabs. Esc and a close control SHALL dismiss the drawer; on
mobile the drawer takes the full width. The board SHALL load orders, requests and payments scoped
to the active branch.

#### Scenario: Open and close the order drawer

- **WHEN** the user clicks a purchase-order row or card
- **THEN** the drawer opens on that order's detail, and Esc or the close control returns to the list

#### Scenario: Switch areas

- **WHEN** the user selects the Solicitudes or Proveedores tab
- **THEN** the board shows that area without leaving the Compras screen

### Requirement: Compras stats and filters

The Órdenes area SHALL show live figures computed from the loaded branch orders — counts of orders
by status (creada, parcialmente recibida, recibida) and the total **por pagar** (sum of outstanding
balances) — and SHALL filter the order list by supplier, order status and a search string (supplier
name or order reference). Active filters SHALL render as dismissable chips with a clear-all control;
filters combine (AND) and apply live.

#### Scenario: Filters combine

- **WHEN** the user picks a supplier, the "parcialmente recibida" status and types a reference fragment
- **THEN** the list shows only orders matching all three and chips for each active filter

#### Scenario: Stats reflect loaded data

- **WHEN** a receipt or a payment changes an order's status or balance
- **THEN** the stat counts and the "por pagar" total update without a page reload

### Requirement: Receipt-progress bar

Every order figure (table rows, cards, and the drawer's header) SHALL render the receipt-progress
bar: a thin bar whose fill maps received-vs-ordered quantity from the `receiptProgress` derivation,
colored by state (creada / warn when partially received / success when fully received).

#### Scenario: Bar reflects partial receipt

- **WHEN** an order has received part but not all of its ordered quantity
- **THEN** its progress bar renders partially filled in the warn color and the row is tinted accordingly

#### Scenario: Bar reflects full receipt

- **WHEN** an order is fully received
- **THEN** its progress bar renders full in the success color

### Requirement: Order detail drawer

The drawer SHALL present the selected order over three tabs: **Detalles** (supplier, status, total,
outstanding balance and progress), **Ítems** (each line's ingredient label, ordered and received
quantities), and **Pagos** (the payment timeline with amounts, methods and the outstanding figure
from `outstandingBalance`). Item and payment labels SHALL resolve through the store's label getters.

#### Scenario: Ítems tab shows received progress per line

- **WHEN** the user opens the Ítems tab of a partially received order
- **THEN** each line shows its ordered and received quantities

#### Scenario: Pagos tab shows the outstanding balance

- **WHEN** the user opens the Pagos tab of an order with payments below its total
- **THEN** the registered payments are listed and the outstanding balance is shown

### Requirement: Receive and pay from the board

The board SHALL let an authorized user receive goods through a **Recibir mercancía** modal (per-item
counted quantities, with the registering employee `Select`) that calls the receive action, and
register a payment through a **Registrar pago** modal (amount, method, employee). Receiving SHALL
require `purchasing.manage`; a receive that exceeds outstanding ordered quantity or a payment without
an open cash session SHALL surface a friendly error and leave the order unchanged.

#### Scenario: Receiving updates progress and stock

- **WHEN** an authorized user receives a quantity for an order's items
- **THEN** the order's received quantities and progress bar update, and the receipt records the
  inventory stock-in already produced by the backend

#### Scenario: Registering a payment reduces the outstanding balance

- **WHEN** an authorized user registers a payment below the order total
- **THEN** the payment appears in the Pagos tab and the outstanding balance decreases

### Requirement: Solicitudes area

The Solicitudes area SHALL list the branch's purchase requests bucketed by status
(pendiente/aprobada/rechazada), let an authorized user create a request, approve or reject a pending
request (gated `purchasing.approve`), and create a purchase order from an approved request. Approve,
reject and order-creation controls SHALL be hidden without the required permission.

#### Scenario: Approve then create an order

- **WHEN** a user with `purchasing.approve` approves a pending request and creates an order from it
- **THEN** the request moves to aprobada and the new order appears in the Órdenes area

#### Scenario: Requests read-only without approve

- **WHEN** the user has `purchasing.read` but not `purchasing.approve`
- **THEN** requests are visible but no approve or reject action is shown

### Requirement: Compras alerts and CSV export

The board SHALL surface an alerts affordance for órdenes con saldo pendiente and órdenes
parcialmente recibidas, each with a quick action (Registrar pago / Recibir), and SHALL export the
current filtered order list to CSV computed client-side.

#### Scenario: Alert quick action

- **WHEN** an order has an outstanding balance
- **THEN** it appears in the alerts area with a Registrar pago quick action

#### Scenario: Export the filtered list

- **WHEN** the user exports while filters are active
- **THEN** the CSV contains only the currently filtered orders

## MODIFIED Requirements

### Requirement: Permission gating and navigation

The Compras board SHALL be reachable at `/purchasing` only for authenticated users with
`purchasing.read`, exposed via a single navigation entry; create-request/create-order/receive/pay
controls SHALL require `purchasing.manage`, and approve/reject SHALL require `purchasing.approve`.
The former `/procurement` route SHALL redirect to `/purchasing`. This gating is UX — the backend
enforces authorization independently.

#### Scenario: Read-only Compras user

- **WHEN** the current user has `purchasing.read` but neither `purchasing.manage` nor
  `purchasing.approve`
- **THEN** orders, requests, items, and payments are visible read-only and no create, approve,
  reject, receive, or pay actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `purchasing.read` navigates to `/purchasing`
- **THEN** the router redirects them to the forbidden view

#### Scenario: Legacy procurement route redirects

- **WHEN** a user navigates to `/procurement`
- **THEN** the router redirects them to `/purchasing`
