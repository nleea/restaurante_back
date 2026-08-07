# storefront-public-api

## Purpose

Public, subdomain-scoped, no-auth endpoints that power the customer storefront: they serve the saved
appearance config and a customer-safe menu read-model, and accept a storefront order (composing
customer + order + items + addons + delivery in one transaction on a per-tenant system employee). The
tenant is resolved from the request subdomain, as `/auth/login` does; no permission is required.
## Requirements
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
customer-safe menu for **the tenant's primary branch**: active categories in order, and for
each active/sellable product its name, description, image, that branch's price, sellable
variant id, available addons (id, name, price), and its recipe-derived removable ingredients
filtered to `is_customer_removable = true`. It MUST NOT expose cost, BOM quantities, or other
internal fields. This code-less form is retained for single-branch tenants; the
branch-addressed form is `GET /storefront/{branch_code}/menu`.

#### Scenario: Returns active products with public fields

- **WHEN** an unauthenticated request reads `GET /storefront/menu`
- **THEN** the response lists active categories and their active products, each with name,
  description, image, price, sellable variant id, and available addons

#### Scenario: Code-less form resolves the primary branch

- **WHEN** an unauthenticated request reads `GET /storefront/menu` on a tenant with several
  active branches
- **THEN** the response is the primary branch's menu, identical to
  `GET /storefront/{primary_code}/menu`

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

### Requirement: Public order intake rejects when the caja is closed

The public storefront order endpoint SHALL reject an order when the resolved branch has no open cash session, returning the distinct "caja cerrada" error (HTTP 409) so the customer-facing UI can show a closed state. No order is created.

#### Scenario: Customer orders while the caja is closed

- **WHEN** a customer submits a storefront order and the branch has no open cash session
- **THEN** the request is rejected with the closed-caja error (409) and no order is created

#### Scenario: Customer orders while the caja is open

- **WHEN** a customer submits a storefront order and the branch has an open cash session
- **THEN** the order is created and stamped with that session

### Requirement: Storefront exposes hours and next opening

The public storefront SHALL expose the business's structured operating hours and, when the caja is closed, the next opening time, so the customer-facing closed state can show "cerrado · abrimos a las X". The business name and photo shown SHALL be sourced from the business profile.

#### Scenario: Closed state shows next opening

- **WHEN** the storefront is loaded while the branch's caja is closed
- **THEN** it can display that ordering is closed and the next opening time from the structured hours

#### Scenario: Name and photo from the profile

- **WHEN** the storefront renders the business identity
- **THEN** the name and photo come from the business profile (single source), not a separate appearance copy

### Requirement: Branch-addressable public menu

`GET /storefront/{branch_code}/menu` SHALL return the customer-safe menu read-model for the
branch whose `branches.code` matches `{branch_code}` within the subdomain tenant,
unauthenticated. The payload shape MUST equal the code-less menu endpoint's; only the branch
whose prices and availability are read changes. Hours and next-opening data returned with
the menu SHALL be those of the addressed branch.

#### Scenario: Menu resolves the addressed branch

- **WHEN** an unauthenticated request reads `GET /storefront/centro/menu` on a tenant that
  has an active branch with code `centro`
- **THEN** the response is that branch's customer-safe menu, with that branch's prices and
  availability

#### Scenario: Two branches return different menus

- **WHEN** the same tenant's branches `centro` and `norte` have different prices or active
  products
- **THEN** `GET /storefront/centro/menu` and `GET /storefront/norte/menu` return the
  respective branch's data, not the primary branch's

#### Scenario: Hours belong to the addressed branch

- **WHEN** the addressed branch is closed but another branch of the tenant is open
- **THEN** the response reports the addressed branch as closed with its own next opening

### Requirement: Branch-addressable public order intake

`POST /storefront/{branch_code}/orders` SHALL create an order on the branch whose
`branches.code` matches `{branch_code}` within the subdomain tenant, applying every rule of
the existing public order intake (find-or-create customer by phone, system employee, payment
method as intent, pending staff confirmation, delivery attachment, caja-closed rejection).
The branch SHALL be taken from the path only; the request body SHALL NOT be able to select a
branch.

#### Scenario: Order lands on the addressed branch

- **WHEN** an unauthenticated customer submits a valid cart to
  `POST /storefront/centro/orders`
- **THEN** the created order, its items and any delivery belong to the branch with code
  `centro`

#### Scenario: Body cannot override the branch

- **WHEN** a submission to `POST /storefront/centro/orders` includes any branch-like field
  in its body
- **THEN** the order is still created on the branch addressed in the path

#### Scenario: Caja gate applies per branch

- **WHEN** the addressed branch has no open cash session while another branch of the tenant
  does
- **THEN** the request is rejected with the caja-closed response, and no order is created

### Requirement: Unknown or inactive branch code is rejected

Any branch-addressed storefront endpoint SHALL respond `404` when `{branch_code}` matches no
branch of the subdomain tenant, or matches a branch that is not active. It SHALL NOT fall
back to the tenant's primary branch or to any other branch.

#### Scenario: Unknown code 404s

- **WHEN** a request addresses a branch code that does not exist for the tenant
- **THEN** the system responds 404 and creates nothing

#### Scenario: Inactive branch 404s

- **WHEN** a request addresses the code of a branch whose `is_active` is false
- **THEN** the system responds 404

#### Scenario: No silent fallback on order intake

- **WHEN** an order is submitted to an unknown branch code
- **THEN** no order is created on the primary branch or on any other branch

### Requirement: Public branch listing

`GET /storefront/branches` SHALL return, unauthenticated and scoped to the subdomain tenant,
the tenant's **active** branches with their `code`, `name` and `address`. It MUST NOT expose
internal fields.

#### Scenario: Lists active branches for a picker

- **WHEN** an unauthenticated request reads `GET /storefront/branches`
- **THEN** the response lists each active branch's code, name and address

#### Scenario: Inactive branches are excluded

- **WHEN** a branch is inactive
- **THEN** it does not appear in the listing

### Requirement: Branch codes are URL-safe

`branches.code` SHALL be accepted only in URL-safe slug form — lowercase letters, digits and
single hyphens between them (`^[a-z0-9]+(-[a-z0-9]+)*$`), at most 32 characters. Writes that
violate the format SHALL be rejected with a validation error. Uniqueness per tenant is
unchanged.

#### Scenario: Slug-form code is accepted

- **WHEN** a branch is created or updated with code `centro-norte`
- **THEN** the write succeeds

#### Scenario: Non-slug code is rejected

- **WHEN** a branch is created or updated with a code containing spaces, uppercase letters
  or punctuation (e.g. `Sede #1 (Centro)`)
- **THEN** the write is rejected with a validation error and the branch is not changed

### Requirement: Store token resolution

`GET /storefront/session/{token}` SHALL return, unauthenticated and scoped to the subdomain
tenant, the contact name and phone bound to a valid store token, together with the branch the
token was minted for. It SHALL respond 404 for an unknown or expired token, and SHALL NOT
expose orders, history, or any other customer data.

#### Scenario: A valid token resolves the contact

- **WHEN** the storefront resolves a token minted for a WhatsApp contact
- **THEN** the response carries that contact's name, phone and branch

#### Scenario: An expired token is not found

- **WHEN** the token's lifetime has passed
- **THEN** the endpoint responds 404

#### Scenario: An unknown token is not found

- **WHEN** a token matching no conversation is resolved
- **THEN** the endpoint responds 404

#### Scenario: Only contact fields are returned

- **WHEN** a token is resolved
- **THEN** the payload contains no order, no order history and no internal identifiers beyond
  what the checkout needs

### Requirement: Orders placed with a token link to the WhatsApp contact

Public order intake SHALL accept an optional store token and, when it is valid, link the
created order to the WhatsApp contact it resolves to. When the token is absent, expired or
unknown, the order SHALL still be created, matching the customer by phone as it does today.

#### Scenario: A tokenised order is linked

- **WHEN** an order is submitted with a valid token
- **THEN** the created order carries the WhatsApp contact the token resolves to

#### Scenario: A token-less order still works

- **WHEN** an order is submitted with no token
- **THEN** the order is created and the customer is matched by phone, unlinked to any WhatsApp
  contact

#### Scenario: An expired token does not block the order

- **WHEN** an order is submitted with an expired token
- **THEN** the order is created normally, matched by phone, and no link is recorded

#### Scenario: A token cannot override the branch

- **WHEN** a token minted for one branch is used on another branch's intake endpoint
- **THEN** the order is created on the branch addressed in the path, and the mismatched token
  does not link the order

### Requirement: Public receipt upload bound to the order's edit token

The public API SHALL accept a receipt image for the order behind an edit token, with the file
travelling through the API so its type and size are checked before anything is stored.

The order SHALL come from the token and SHALL NOT be a parameter of the request. An expired,
unknown or foreign token SHALL be refused with the same answer as any other, revealing nothing
about whether the order exists.

#### Scenario: A receipt is accepted for the order behind the link

- **WHEN** a customer uploads a receipt with a valid edit token
- **THEN** the file is stored against that order and no other

#### Scenario: A file that is not an acceptable receipt is refused

- **WHEN** the upload is not an accepted image type, or exceeds the size limit
- **THEN** it is refused before being stored

#### Scenario: A dead link uploads nothing

- **WHEN** the token is expired or unknown
- **THEN** the upload is refused and nothing is stored

### Requirement: Public payment declaration by token

The public API SHALL accept a declaration that the customer paid: the amount, the method, and the
receipt already uploaded. It SHALL return the order as it stands, unchanged in money terms.

The declared amount SHALL NOT be trusted as a payment. What the response reports as owed SHALL
be the same before and after declaring.

#### Scenario: Declaring reports the order unchanged

- **WHEN** a customer declares a payment
- **THEN** the response shows the same total and the same amount owed as before

#### Scenario: The customer can see their declaration is pending

- **WHEN** the order is read after declaring
- **THEN** it reports that a declaration is awaiting confirmation

### Requirement: The checkout carries the receipt it asks for

When the public order intake receives a receipt for a method that requires proof, it SHALL record
it as a payment declaration on the created order.

#### Scenario: An attached receipt survives the order

- **WHEN** an order is created with a receipt attached
- **THEN** the created order carries a pending declaration with that receipt

#### Scenario: No receipt is still a valid order

- **WHEN** an order is created without a receipt
- **THEN** the order is created exactly as it is today

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

### Requirement: Public delivery intake defers price and payment method

The public storefront API SHALL accept a delivery order containing customer contact, products and location without a payment-method selection. It SHALL create the order and delivery record pending quote, return a response that does not claim a final payable total, and preserve the provided GPS coordinates when present.

#### Scenario: Customer submits address without choosing payment

- **WHEN** a customer submits a delivery order with a written address and no payment method
- **THEN** the API creates the order successfully and returns that its delivery value will be confirmed later

#### Scenario: Customer submits a GPS point

- **WHEN** a customer submits a delivery order with latitude and longitude
- **THEN** those coordinates are stored for later quotation without waiting for a quote result

### Requirement: A payment request endpoint has narrow authority

The public API SHALL expose a token-authenticated payment-request surface that shows the current quoted amount, lets the customer select a supported payment method, and lets them declare/send a payment proof. It SHALL reject expired, consumed or invalidated tokens and SHALL NOT expose order editing or another customer's information.

#### Scenario: Customer chooses transfer from a valid request

- **WHEN** a customer opens a valid payment request and selects transfer
- **THEN** the order records transfer as an intent and the customer can declare a payment with its current outstanding amount

#### Scenario: Expired request reveals no payment action

- **WHEN** a customer opens an expired payment request token
- **THEN** the API refuses the request and exposes no ability to change payment intent or submit a proof

### Requirement: Public table resolution by branch and table code

`GET /storefront/{branch_code}/tables/{table_code}` SHALL resolve a dining table without
authentication, scoped to the subdomain tenant, and return the table's number, its branch, and
whether the business can take orders right now (open cash session and open business hours).

The branch and the table both come from the URL, never from a payload — the same rule the public
menu already defends. A table travelling in the request body would let somebody order to table 5
while looking at another branch's menu; in the path, the order cannot contradict the menu that was
seen.

Resolution SHALL NOT change the table's status.

An unknown or inactive table code, or a table that does not belong to the addressed branch, SHALL be
rejected with 404 Not Found. It MUST NOT fall back to any other table, for the same reason branch
resolution never falls back to the primary branch.

#### Scenario: Resolve a table from its QR
- **WHEN** an unauthenticated request resolves an active table code under its branch code
- **THEN** the table's number and branch are returned, together with whether orders can be taken now

#### Scenario: Reject a table code from another branch
- **WHEN** a table code that belongs to a different branch is resolved under this branch code
- **THEN** the system responds 404 Not Found and no table is returned

#### Scenario: Reject an unknown or inactive table
- **WHEN** an unknown or deactivated table code is resolved
- **THEN** the system responds 404 Not Found

#### Scenario: Resolving is read-only
- **WHEN** a table is resolved
- **THEN** its status is unchanged

### Requirement: Public table order intake fires to the kitchen

`POST /storefront/{branch_code}/tables/{table_code}/orders` SHALL create a real order without
authentication, scoped to the subdomain tenant. It SHALL require a diner name and at least one line;
it SHALL NOT require a phone number and SHALL NOT create or reuse a `customers` record.

It SHALL open the order on the tenant's system employee with channel `dine_in`, `origin` `qr`, the
resolved `dining_table_id`, the given `diner_name`, and no payment method — table orders are paid on
close. It SHALL add each line with its addons and kitchen note (ingredient removals folded into the
note, composed by the server), mint the order's edit token, and **route the order to the kitchen in
the same operation**.

Routing is the deliberate difference from web intake, which leaves an order pending staff
confirmation. A web order is placed by a stranger at a distance and deserves a human look before
ingredients are spent; a table order is confirmed by someone sitting in the dining room in front of
the food they will pay for. The diner performs the review that staff perform for a web order.

No `order_payments` row is created at intake: money is received when the bill is settled.

#### Scenario: A confirmed table order is created and fired
- **WHEN** an unauthenticated diner confirms a valid cart on a resolved table
- **THEN** a `dine_in` order is created with that table, diner name and `origin` `qr`
- **AND** kitchen tickets exist for its items in the same operation
- **AND** the order is open, unpaid, and carries an edit token

#### Scenario: No phone, no customer record
- **WHEN** a table order is placed
- **THEN** it is accepted with no phone number and its `customer_id` is null

#### Scenario: Confirming again adds a round
- **WHEN** the diner adds items through their edit token and confirms
- **THEN** only the added items are routed, as separate tickets

#### Scenario: Empty or invalid cart is rejected
- **WHEN** a submission has no line items or references a non-sellable/unknown product
- **THEN** the system responds with a validation error and creates no order and no ticket

#### Scenario: Removals ride in the kitchen note
- **WHEN** a cart line excludes ingredients (e.g. "sin cebolla")
- **THEN** the created order item's kitchen note conveys those removals so the kitchen sees them

### Requirement: Table intake refuses when the business cannot serve

Table order intake SHALL be refused when the branch has no open cash session, with the same
`cash_closed` conflict the existing public intake returns, and the refusal SHALL be phrased for a
customer rather than as a system error.

Table resolution SHALL report that state **before** the diner builds a cart. A diner who assembles
an order and is rejected at the last step has been made to waste their time by a condition the
system knew from the first request.

#### Scenario: Closed caja is told up front
- **WHEN** a table is resolved while its branch has no open cash session
- **THEN** the response says orders cannot be taken now, before any menu interaction

#### Scenario: Closed caja still refuses intake
- **WHEN** a table order is submitted while the branch has no open cash session
- **THEN** the system refuses it and creates no order

