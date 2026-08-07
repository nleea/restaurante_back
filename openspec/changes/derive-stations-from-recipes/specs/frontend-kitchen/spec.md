## MODIFIED Requirements

### Requirement: Station and product mapping setup

The KitchenView SHALL let an authorized user create, rename, reorder and activate the branch's
kitchen stations; these setup controls SHALL be available only with the `kitchen.update`
permission.

Assigning a product to a station SHALL NOT live here. It belongs beside the dish in the carta,
where the person already is when the need arises — sending them to a separate configuration
section is the step that does not happen, and a dish nobody prepares is invisible until it has
already been sold. The KitchenView SHALL instead surface **which products still have no station**
and point at the carta to fix them.

Station order SHALL be expressed as a position in the line, moved one step at a time, rather than
a number the user has to keep track of. A new station SHALL be created at the end of the line.

#### Scenario: Create a station

- **WHEN** a user with `kitchen.update` creates a station with a name
- **THEN** the station is created at the end of the line and appears in the station list

#### Scenario: Rename a station in place

- **WHEN** a user with `kitchen.update` edits a station's name
- **THEN** the new name is persisted
- **AND** a blank name is rejected without overwriting the existing one

#### Scenario: Reorder the line

- **WHEN** a user moves a station one step up or down
- **THEN** it swaps position with its neighbour, and the first cannot move up nor the last down

#### Scenario: Products nobody prepares are listed first

- **WHEN** the branch has products with no station mapping
- **THEN** the screen leads with them, counted, distinguishing the ones already on sale from
  drafts with no active variants
- **AND** offers a way through to the carta, where the assignment is made

#### Scenario: Nothing pending

- **WHEN** every product has at least one station
- **THEN** no pending block is rendered

## REMOVED Requirements

### Requirement: Attach and edit product mappings from the KitchenView

**Reason**: Moved to the carta (`frontend-menu`), next to the dish being created. The product
picker here required knowing which product you wanted before opening the screen, and offered no
recipe context to answer "what does this station owe this dish?" — so it was the worse of two
places to do the same job.

**Migration**: Use the stations panel in the product editor of the carta, which now edits role and
tasks and can derive both from the dish's recipe.
