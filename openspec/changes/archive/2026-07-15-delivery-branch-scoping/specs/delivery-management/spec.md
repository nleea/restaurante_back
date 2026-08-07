## MODIFIED Requirements

### Requirement: Tenant and branch isolation for delivery

The system SHALL scope every delivery read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate routes, runs or deliveries of another tenant.

Delivery records, dispatch runs and route drivers SHALL each carry a `branch_id`, like the routes and branch settings they belong with, so the operational records of one branch are separable from another's.

That `branch_id` SHALL be **derived by the system, never accepted from the request**: a delivery record takes the branch of its order; a run and a route driver take the branch of their route. No create or update request SHALL carry a `branch_id` for these records.

Listing delivery records and listing runs SHALL require a `branch_id` and SHALL return only the records of that branch. It SHALL NOT be possible to list every delivery record or run of a tenant across branches.

#### Scenario: Tenant cannot see another tenant's routes
- **WHEN** a request for tenant A lists delivery routes
- **THEN** only routes whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a route id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a delivery endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

#### Scenario: A delivery record takes its order's branch
- **WHEN** a delivery record is created for an order of branch A
- **THEN** the delivery record's branch is A, without the request naming it

#### Scenario: A run and a route driver take their route's branch
- **WHEN** a run is created for a route of branch A, or a driver is attached to that route
- **THEN** the run and the route driver carry branch A, without the request naming it

#### Scenario: Listing is scoped to one branch
- **WHEN** delivery records or runs are listed for branch A of a tenant that also operates branch B
- **THEN** only branch A's records are returned, and branch B's are absent

#### Scenario: Listing without a branch is rejected
- **WHEN** delivery records or runs are listed with no branch given
- **THEN** the system rejects the request rather than returning the tenant's records across branches

### Requirement: Assignment and delivery lifecycle

The system SHALL support an explicit delivery lifecycle. Assigning a delivery to a `preparing` run sets the delivery's route and run and moves it to `assigned`. Departing a run moves it `preparing → in_transit` (stamping `departed_at`) and moves its `assigned` deliveries to `in_transit`. A delivery can then be marked `delivered` or `not_delivered` (stamping `delivered_at`). Finishing a run moves it `in_transit → finished`. Backward or out-of-order transitions SHALL be rejected.

A delivery SHALL be assignable only to a run of **its own branch**. A cross-branch assignment SHALL be rejected as a conflict, leaving both records untouched.

#### Scenario: Assign a delivery to a run
- **WHEN** an authorized user assigns a `pending` delivery to a `preparing` run
- **THEN** the delivery's run and route are set and its status becomes `assigned`

#### Scenario: Reject assigning to a departed run
- **WHEN** a user assigns a delivery to a run that is not `preparing`
- **THEN** the system responds with a conflict error

#### Scenario: Reject assigning to a run of another branch
- **WHEN** a user assigns a delivery of branch A to a run of branch B
- **THEN** the system responds with a conflict error and neither the delivery nor the run changes

#### Scenario: Depart a run
- **WHEN** an authorized user departs a `preparing` run
- **THEN** the run becomes `in_transit` with `departed_at` set
- **AND** its `assigned` deliveries become `in_transit`

#### Scenario: Mark a delivery delivered
- **WHEN** an authorized user marks an `in_transit` delivery as delivered
- **THEN** its status becomes `delivered` with `delivered_at` set

#### Scenario: Mark a delivery not delivered
- **WHEN** an authorized user marks an `in_transit` delivery as not delivered
- **THEN** its status becomes `not_delivered` with `delivered_at` set

#### Scenario: Finish a run
- **WHEN** an authorized user finishes an `in_transit` run
- **THEN** the run becomes `finished` with `finished_at` set

#### Scenario: Reject finishing a non-in-transit run
- **WHEN** a user finishes a run that is not `in_transit`
- **THEN** the system responds with a conflict error
