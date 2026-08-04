## ADDED Requirements

### Requirement: Tenant and branch isolation for kitchen

The system SHALL scope every kitchen read and write to the `tenant_id` resolved by the subdomain middleware, and SHALL validate that any provided `branch_id` belongs to that tenant. No request SHALL read or mutate stations or tickets of another tenant.

#### Scenario: Tenant cannot see another tenant's stations
- **WHEN** a request for tenant A lists kitchen stations
- **THEN** only stations whose `tenant_id` equals tenant A are returned

#### Scenario: Cross-tenant lookup is treated as not found
- **WHEN** a request for tenant A fetches a station id that belongs to tenant B
- **THEN** the system responds 404 Not Found

#### Scenario: Request without a resolved tenant is rejected
- **WHEN** a kitchen endpoint is called and no tenant was resolved
- **THEN** the system rejects the request with a tenant-not-resolved error

### Requirement: Manage kitchen stations

The system SHALL allow authorized users to create, list, update and deactivate kitchen stations for a branch, each with a name, a display position, and an active flag.

#### Scenario: Create a station
- **WHEN** an authorized user creates a station for a branch of the current tenant
- **THEN** the station is persisted active and returned

#### Scenario: List stations for a branch
- **WHEN** an authorized user lists stations for a branch
- **THEN** only that branch's stations are returned, ordered by position

#### Scenario: Reject unknown branch
- **WHEN** a user creates a station for a `branch_id` not in the current tenant
- **THEN** the system responds 404 Not Found

### Requirement: Configure product-to-station routing

The system SHALL allow authorized users to map a product to one or more kitchen stations, remove a mapping, and list a product's stations. The product and station MUST belong to the current tenant; the same product-station pair MUST NOT be mapped twice.

#### Scenario: Attach a product to a station
- **WHEN** an authorized user maps an existing product to an existing station
- **THEN** the mapping is persisted

#### Scenario: Reject duplicate mapping
- **WHEN** a user maps a product to a station it is already mapped to
- **THEN** the system responds with a conflict error

#### Scenario: Detach a product from a station
- **WHEN** an authorized user removes an existing product-station mapping
- **THEN** the mapping no longer exists

### Requirement: Route an order to the kitchen

The system SHALL allow authorized users to route an order to the kitchen: for each non-cancelled order item, the system resolves the item's product (via its product variant) and creates a ticket (`order_item_stations`) in state `pending` for each station configured for that product, at the order's branch. Items whose product has no configured station SHALL produce no ticket. Routing SHALL be idempotent — an item already routed to a station SHALL NOT be duplicated.

#### Scenario: Route creates tickets per configured station
- **WHEN** an authorized user routes an order whose item's product is mapped to a station
- **THEN** a `pending` ticket is created for that item at that station

#### Scenario: Item without a configured station produces no ticket
- **WHEN** an order item's product has no station mapping
- **THEN** routing creates no ticket for that item

#### Scenario: Cancelled items are not routed
- **WHEN** an order with a cancelled item is routed
- **THEN** no ticket is created for the cancelled item

#### Scenario: Routing is idempotent
- **WHEN** an order is routed twice
- **THEN** no duplicate tickets are created for an item-station already routed

### Requirement: KDS board and ticket lifecycle

The system SHALL allow authorized users to list a station's tickets (optionally filtered by state) and to advance a ticket through `pending → in_progress → ready`, stamping `ready_at` when it becomes `ready`. Advancing a `ready` ticket SHALL be rejected.

#### Scenario: List a station's pending tickets
- **WHEN** an authorized user lists a station's tickets filtered by `pending`
- **THEN** only that station's pending tickets within the tenant are returned

#### Scenario: Advance a ticket
- **WHEN** an authorized user advances a `pending` ticket
- **THEN** its state becomes `in_progress`

#### Scenario: Mark a ticket ready
- **WHEN** an authorized user advances an `in_progress` ticket
- **THEN** its state becomes `ready` and `ready_at` is set

#### Scenario: Reject advancing a ready ticket
- **WHEN** a user advances a ticket that is already `ready`
- **THEN** the system responds with a conflict error

### Requirement: RBAC protection of kitchen endpoints

The system SHALL require the `kitchen.read` permission for kitchen read endpoints (stations list, product routing list, station board) and the `kitchen.update` permission for writes (manage stations, configure routing, route an order, advance tickets).

#### Scenario: Read without permission
- **WHEN** a user lacking `kitchen.read` calls a kitchen read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Update without permission
- **WHEN** a user lacking `kitchen.update` tries to manage stations, route an order, or advance a ticket
- **THEN** the system responds 403 Forbidden

#### Scenario: Authorized access
- **WHEN** a user holding the required permission calls the corresponding endpoint within their tenant
- **THEN** the system processes the request normally
