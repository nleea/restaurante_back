## MODIFIED Requirements

### Requirement: RBAC protection of delivery endpoints

The system SHALL require `delivery.read` for read endpoints, `delivery.manage` for managing routes, route drivers, branch delivery settings and creating runs, `delivery.address` for reading and writing a single order's delivery record (create and update), and `delivery.assign` for assignment and lifecycle transitions (assign, depart, mark delivered/not delivered, finish).

`delivery.address` SHALL exist so the address can be captured by whoever takes the order without granting delivery administration: a holder of `delivery.address` alone SHALL NOT be able to edit routes, route drivers, branch delivery settings, or create runs.

For backward compatibility with roles provisioned before this split, the delivery-record endpoints SHALL accept **either** of two codes: reading an order's delivery record SHALL accept `delivery.address` or `delivery.read`; creating or updating a delivery record SHALL accept `delivery.address` or `delivery.manage`.

#### Scenario: Read without permission
- **WHEN** a user lacking `delivery.read` calls a delivery read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Manage without permission
- **WHEN** a user lacking `delivery.manage` tries to create a route or a run
- **THEN** the system responds 403 Forbidden

#### Scenario: Assign without permission
- **WHEN** a user lacking `delivery.assign` tries to assign a delivery or advance the lifecycle
- **THEN** the system responds 403 Forbidden

#### Scenario: Address permission writes a delivery record without delivery administration
- **WHEN** a user holding `delivery.address` but neither `delivery.manage` nor `delivery.read` creates or updates a delivery record for an order, and reads that order's delivery record
- **THEN** those requests succeed

#### Scenario: Address permission does not grant delivery administration
- **WHEN** a user holding `delivery.address` but not `delivery.manage` tries to create or edit a route, edit route drivers, patch branch delivery settings, or create a run
- **THEN** the system responds 403 Forbidden

#### Scenario: A pre-existing manage-only role keeps writing delivery records
- **WHEN** a user holding `delivery.manage` but not `delivery.address` creates or updates a delivery record
- **THEN** the request succeeds

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally

## ADDED Requirements

### Requirement: Base roles for delivery address capture

The permission catalog SHALL define `delivery.address` in the `delivery` module, and the base roles SHALL grant it to the roles that take orders — `waiter`, `cashier`, `manager` and `admin` — so the address can be captured at the moment the order is taken.

The `courier` base role SHALL NOT hold `delivery.address`.

Provisioning SHALL remain additive and idempotent: adding this code SHALL NOT require a schema migration, and re-running the RBAC seed SHALL insert the permission and grant it to the base roles without disturbing tenant-custom roles.

#### Scenario: Order-taking base roles gain the permission
- **WHEN** the RBAC seed runs against an installation provisioned before this change
- **THEN** `delivery.address` exists in the permission catalog and the `waiter`, `cashier` and `manager` base roles hold it

#### Scenario: Seeding twice changes nothing further
- **WHEN** the RBAC seed runs a second time
- **THEN** no duplicate permission or role grant is created

#### Scenario: Couriers do not author addresses
- **WHEN** the base roles are provisioned
- **THEN** the `courier` role does not hold `delivery.address`
