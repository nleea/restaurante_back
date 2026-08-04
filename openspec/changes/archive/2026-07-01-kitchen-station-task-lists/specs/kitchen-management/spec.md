# kitchen-management (delta)

## MODIFIED Requirements

### Requirement: Configure product-to-station routing

The system SHALL allow authorized users to map a product to one or more kitchen stations, remove a mapping, list a product's stations, and update an existing mapping's `role` and ordered task list (short task names, e.g. "Carne de hamburguesa", "Tocineta ahumada"; each ≤60 chars, at most 10 per mapping, empty by default). The product and station MUST belong to the current tenant; the same product-station pair MUST NOT be mapped twice.

#### Scenario: Attach a product to a station

- **WHEN** an authorized user maps an existing product to an existing station (optionally with a role and tasks)
- **THEN** the mapping is persisted

#### Scenario: Reject duplicate mapping

- **WHEN** a user maps a product to a station it is already mapped to
- **THEN** the system responds with a conflict error

#### Scenario: Update a mapping's role and tasks

- **WHEN** an authorized user updates an existing mapping with a new role and/or task list
- **THEN** the mapping reflects the new values without being detached and re-attached

#### Scenario: Oversized task list is rejected

- **WHEN** a mapping write carries more than 10 tasks or a task longer than 60 characters
- **THEN** the request fails validation and nothing is stored

#### Scenario: Detach a product from a station

- **WHEN** an authorized user removes an existing product-station mapping
- **THEN** the mapping no longer exists

## ADDED Requirements

### Requirement: Station task lists frozen onto tickets

When routing creates a ticket, the system SHALL copy the mapping's task list onto the ticket
(alongside `role`), frozen at fire time: later edits to the mapping's tasks SHALL NOT alter
tickets already created. Tickets SHALL expose their tasks on the board API so kitchen screens
can render each station's itemized work for the dish.

#### Scenario: Routing copies tasks onto the ticket

- **WHEN** an order is routed and the item's product-station mapping has tasks configured
- **THEN** the created ticket carries that task list and the board API returns it

#### Scenario: Config edits do not rewrite fired tickets

- **WHEN** a mapping's tasks are edited after an order was routed
- **THEN** the existing ticket keeps the tasks captured at fire time; only subsequently routed
  orders carry the new list

#### Scenario: Mapping without tasks

- **WHEN** a mapping has no tasks configured
- **THEN** its tickets carry an empty task list and behave exactly as before this capability
