## ADDED Requirements

### Requirement: Idempotent demo dataset loader

The system SHALL provide a re-runnable command that loads a demo dataset into the database without creating duplicate rows on repeated runs. The loader MUST use select-or-create semantics keyed on natural identifiers (e.g. tenant slug, branch code, ingredient name, route name, customer email) so that running it twice leaves the database in the same state as running it once.

#### Scenario: First run populates an empty database

- **WHEN** the loader runs against a database that has migrations applied but no demo data
- **THEN** it creates the demo tenant, branch, RBAC, and the full operational dataset
- **AND** it commits successfully and prints a summary of rows created per area

#### Scenario: Second run is a no-op for already-seeded rows

- **WHEN** the loader runs a second time against the already-seeded database
- **THEN** it does not raise, does not duplicate any row, and reports the existing entities as already present

### Requirement: Tenant and branch scoping

All seeded business rows SHALL belong to the demo tenant and its branch. The loader MUST set `tenant_id` (and `branch_id` for branch-scoped tables) explicitly on every row, because it runs outside an HTTP request and the automatic tenant filter has no context.

#### Scenario: Branch-scoped rows carry both ids

- **WHEN** the loader creates a branch-scoped row (e.g. an inventory stock, employee, or delivery route)
- **THEN** the row has both `tenant_id` and `branch_id` set to the demo tenant and demo branch
- **AND** no row is written for any other tenant

### Requirement: Supplies (insumos) and inventory stock

The loader SHALL seed a realistic set of supplies (insumos) as `ingredients`, each referencing a seeded unit of measure, and SHALL create an `inventory_stocks` row per supply for the demo branch with a current quantity and a minimum stock level.

#### Scenario: Supplies have units and stock

- **WHEN** the loader seeds supplies
- **THEN** the units of measure lookup is populated first (e.g. kg, g, L, ml, unit)
- **AND** each supply references a valid `unit_of_measure_id`
- **AND** each supply has exactly one `inventory_stocks` row for the demo branch with `current_quantity` and `min_stock` as Decimals

### Requirement: Delivery routes (rutas) with drivers and runs

The loader SHALL seed delivery routes for the demo branch, assign driver employees to them, and create at least one delivery run plus order deliveries that thread sample orders through the explicit delivery states.

#### Scenario: Routes have drivers and deliverable orders

- **WHEN** the loader seeds delivery data
- **THEN** it creates one or more `delivery_routes` with covered zones for the demo branch
- **AND** it links driver employees via `delivery_route_drivers`
- **AND** it creates at least one `delivery_run` and `order_deliveries` rows using valid status values (`preparing` for runs, `pending`/`assigned`/`in_transit`/`delivered` for deliveries)

### Requirement: End-to-end operational chain

The loader SHALL seed the supporting master data and sample transactions required for the cross-module flow so reports and screens are non-empty: staff/drivers, customers, menu products with variants, recipes linking product variants to supplies, sample orders with items and payments, a cash session, and at least one finance expense.

#### Scenario: A sellable product deducts a real supply via its recipe

- **WHEN** the loader seeds menu and recipes
- **THEN** at least one product variant has `recipe_items` referencing seeded supplies with quantities and units
- **AND** at least one order contains that product variant with order items and a payment recorded against an open cash session

#### Scenario: FK ordering is respected

- **WHEN** the loader runs
- **THEN** parent rows are created before children following the required order (units/countries/cities → tenant/branch → persons/users/RBAC/employees → ingredients → stock → suppliers → menu → recipes → customers → routes → tables → orders → payments → deliveries)
- **AND** no foreign-key or RESTRICT violation occurs

### Requirement: Documented run and reset workflow

The change SHALL document how to load and reset the demo dataset, and the minimal seed used by tests MUST remain the default behavior so it is not coupled to the demo dataset.

#### Scenario: Operator can load the demo dataset

- **WHEN** an operator follows the documented command
- **THEN** the demo dataset is loaded via a single command (e.g. `poetry run python -m scripts.seed_demo`)
- **AND** the existing minimal `scripts.seed` continues to work unchanged for the baseline tenant/admin/RBAC
