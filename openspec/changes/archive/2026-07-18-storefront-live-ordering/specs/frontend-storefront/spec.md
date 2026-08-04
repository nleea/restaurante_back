## ADDED Requirements

### Requirement: Storefront themed by the saved appearance config

The `/store` view SHALL fetch the tenant's appearance config from the public API and apply its
theme (colors, font) as CSS variables and its block layout (flattened to a single mobile column via
`gridToLinearOrder`), instead of the mock config. It SHALL render a usable page while the config
loads and if the fetch fails (falling back to defaults), never a blank error.

#### Scenario: Real config themes the page

- **WHEN** a customer opens `/store` for a tenant with a saved config
- **THEN** the page renders in that tenant's palette/font with its configured, ordered blocks

#### Scenario: Graceful load/failure state

- **WHEN** the appearance fetch is pending or fails
- **THEN** the page shows a loading or default-themed state, not a blank screen or crash

### Requirement: Storefront renders the real menu

The `/store` carta SHALL render the tenant's real menu from the public menu endpoint — categories,
products (name, description, image, price), product detail with real available addons and
recipe-derived removable ingredients — replacing the mock carta. Search and category navigation
operate over the real data.

#### Scenario: Real products appear

- **WHEN** the menu loads
- **THEN** the carta lists the tenant's real categories and active products with their real prices
  and images

#### Scenario: Product detail shows real addons and removables

- **WHEN** a customer opens a product's detail
- **THEN** the addons and the "quitar ingredientes" list come from that product's real data (addons
  and flag-filtered recipe ingredients)

#### Scenario: Empty menu state

- **WHEN** the tenant has no published products
- **THEN** the carta shows a clear empty state rather than mock dishes

### Requirement: Checkout places a real order

The storefront checkout SHALL submit the assembled cart (line items with quantity, addons, chosen
removals, note; fulfillment type and address/GPS; customer contact) to `POST /storefront/orders`,
and the confirmation SHALL display the real order number and status returned by the API. Submission
errors SHALL be surfaced without losing the cart.

#### Scenario: Successful order shows the real number

- **WHEN** a customer completes checkout
- **THEN** the storefront POSTs the order and the confirmation shows the server-returned order
  number and initial status

#### Scenario: Submission error keeps the cart

- **WHEN** the order submission fails
- **THEN** the customer sees an error and the cart contents are preserved for retry
