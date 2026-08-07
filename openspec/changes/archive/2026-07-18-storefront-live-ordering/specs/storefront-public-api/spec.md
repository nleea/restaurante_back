## ADDED Requirements

### Requirement: Public appearance endpoint

`GET /storefront/appearance` SHALL return the tenant's saved appearance config (or the default when
none is saved), resolving the tenant from the request subdomain, WITHOUT requiring authentication or
any permission. The response shape MUST equal the admin appearance config (same JSON contract).

#### Scenario: Anonymous read returns the saved config

- **WHEN** an unauthenticated request hits `GET /storefront/appearance` on a tenant subdomain that
  has a saved config
- **THEN** the system returns that config with 200 and no auth challenge

#### Scenario: Default when unconfigured

- **WHEN** an unauthenticated request reads the appearance of a tenant that never saved one
- **THEN** the system returns a valid default config (never 404)

### Requirement: Public menu read-model

`GET /storefront/menu` SHALL return, unauthenticated and scoped to the subdomain tenant, a
customer-safe menu: active categories in order, and for each active/sellable product its name,
description, image, primary-branch price, sellable variant id, available addons (id, name, price),
and its recipe-derived removable ingredients filtered to `is_customer_removable = true`. It MUST NOT
expose cost, BOM quantities, or other internal fields.

#### Scenario: Returns active products with public fields

- **WHEN** an unauthenticated request reads `GET /storefront/menu`
- **THEN** the response lists active categories and their active products, each with name,
  description, image, price, sellable variant id, and available addons

#### Scenario: Removable ingredients honor the flag

- **WHEN** a product's variant recipe includes an ingredient with `is_customer_removable = false`
  (e.g. salt)
- **THEN** that ingredient is absent from the product's removable list, while flagged-removable
  ingredients are present

#### Scenario: Inactive items are excluded

- **WHEN** a product or category is inactive
- **THEN** it does not appear in the public menu

#### Scenario: No internal fields leak

- **WHEN** the public menu is returned
- **THEN** no ingredient cost, recipe quantity, or non-public field is present in the payload

### Requirement: Public order intake

`POST /storefront/orders` SHALL create a real order from a customer cart without authentication,
scoped to the subdomain tenant. It SHALL require a customer name and phone, find-or-create the
customer by phone, open an order on the tenant's system employee with channel `takeaway` (pickup) or
`delivery`, record the customer's chosen payment method as an intent on the order
(`orders.payment_method`), add each cart line with its selected addons and a kitchen note (chosen
ingredient removals folded into the note), and, for delivery, attach a delivery with the given
address / coordinates. It SHALL return an order identifier/number and the initial status. The order
SHALL be created unpaid and left **pending staff confirmation** — its items SHALL NOT auto-fire to
the kitchen; staff confirm and fire them (a delivery order still enters Dispatch as pending). No
`order_payments` row is created at intake (that models money actually received).

#### Scenario: Pickup order is created

- **WHEN** an unauthenticated customer submits a pickup cart with valid line items
- **THEN** the system creates a `takeaway` order with those items and addons and returns an order
  number with an initial (open/pending) status

#### Scenario: Order lands pending, not auto-fired

- **WHEN** a storefront order is created
- **THEN** its items are pending (not routed to the kitchen) and become visible for staff to confirm
  and fire, exactly like a not-yet-fired staff order

#### Scenario: Payment method is recorded as intent

- **WHEN** a customer picks a payment method at checkout
- **THEN** the created order carries that method in `orders.payment_method`, and no `order_payments`
  row is created until staff register a real payment

#### Scenario: Delivery order attaches delivery info

- **WHEN** a customer submits a delivery cart with an address (or GPS coordinates)
- **THEN** the system creates a `delivery` order and attaches a delivery carrying that address /
  coordinates

#### Scenario: Removals ride in the kitchen note

- **WHEN** a cart line excludes ingredients (e.g. "sin cebolla")
- **THEN** the created order item's kitchen note conveys those removals so the kitchen sees them

#### Scenario: Customer is reused by phone

- **WHEN** two orders are placed with the same phone number
- **THEN** both link to the same customer record (created once, reused thereafter)

#### Scenario: Empty or invalid cart is rejected

- **WHEN** a submission has no line items or references a non-sellable/unknown product
- **THEN** the system responds with a validation error and creates no order

### Requirement: System employee for web orders

Web orders SHALL be attributed to a per-tenant system employee (created on demand if absent), so the
non-null `orders.employee_id` is satisfied without a logged-in user and without a schema change.

#### Scenario: System employee is resolved or created

- **WHEN** the first storefront order for a tenant is created
- **THEN** the system resolves an existing web-orders employee or creates one, and attributes the
  order to it; subsequent orders reuse the same employee
