## ADDED Requirements

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

## MODIFIED Requirements

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
