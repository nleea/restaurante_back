## ADDED Requirements

### Requirement: Assign kitchen stations to a product from the menu

The menu screen SHALL let a user with the kitchen configuration permission map a product to one or
more kitchen stations, remove a mapping, and set each mapping's role and ordered task list. The
available stations SHALL be the ones already configured for the branch; the screen SHALL NOT
invent or create stations.

It lives in the menu and not in a separate kitchen setup because the moment it is needed is while
creating the dish, and that is where the person already is. Sending them to another section to
finish the configuration is precisely the step that does not happen today — which is how a dish
ends up sellable and invisible to the kitchen.

Without the permission the mappings are visible but not editable, so anyone reading the menu can
still tell where a dish is prepared.

#### Scenario: Map a product to a station
- **WHEN** a user with the kitchen configuration permission assigns a station to a product
- **THEN** the mapping is saved and shown on that product

#### Scenario: Set what the station does for that product
- **WHEN** the user gives a mapping a role and a list of tasks
- **THEN** they are saved with the mapping and shown with it

#### Scenario: Remove a mapping
- **WHEN** the user removes a station from a product
- **THEN** the mapping disappears from that product

#### Scenario: Read-only without the permission
- **WHEN** a user without the kitchen configuration permission opens a product
- **THEN** they see its stations but no control to change them

### Requirement: The menu shows which products cannot be sold yet

The menu SHALL mark the products that have no kitchen station, stating that they cannot be sold
until one is assigned, and SHALL make them findable without opening every product one by one.

A missing station is invisible by nature — the dish looks complete on the menu and only stops
existing when the kitchen should have received it. Marking it turns a failure discovered by a
paying customer into a list someone clears in two minutes.

#### Scenario: A product with no station is marked
- **WHEN** a user opens a product with no kitchen station
- **THEN** the screen says it cannot be sold until a station is assigned, and offers to assign one

#### Scenario: The pending ones are findable together
- **WHEN** a user looks at the menu with products missing a station
- **THEN** those products are identifiable without opening each one

#### Scenario: Refusing to activate says what is missing
- **WHEN** a user tries to activate a variant whose product has no station
- **THEN** the screen states that a kitchen station is required and where to assign it, rather
  than only reporting a failure
