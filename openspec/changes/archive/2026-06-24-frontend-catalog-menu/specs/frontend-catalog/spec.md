## ADDED Requirements

### Requirement: Catalog route is permission-gated

The system SHALL expose a `/catalog` route that requires authentication and the `catalog.read`
permission. The route MUST be reachable from the authenticated app navigation only when the current
user holds `catalog.read`.

#### Scenario: User without catalog.read is blocked

- **WHEN** an authenticated user lacking `catalog.read` navigates to `/catalog`
- **THEN** the router redirects to the `forbidden` (`/403`) route and no catalog data is fetched

#### Scenario: User with catalog.read reaches the screen

- **WHEN** an authenticated user holding `catalog.read` navigates to `/catalog`
- **THEN** the Catalog screen renders and loads the list of units of measure

### Requirement: Browse units of measure

The Catalog screen SHALL list units of measure following the mobile-first master–detail pattern,
distinguishing base units from derived units (which display their base unit and conversion factor).

#### Scenario: List shows base and derived units

- **WHEN** the units list loads
- **THEN** each base unit is shown without a conversion factor and each derived unit shows its base
  unit and conversion factor

#### Scenario: Drill into a unit on mobile

- **WHEN** the viewport is `< lg` and the user taps a unit row
- **THEN** the detail view fills the screen with a back affordance returning to the list

### Requirement: Manage units of measure

The system SHALL allow a user with `catalog.manage` to create and edit units of measure. A derived
unit MUST reference an existing base unit and carry a conversion factor; a base unit MUST NOT carry a
conversion factor. Users with only `catalog.read` MUST see read-only views.

#### Scenario: Create a base unit

- **WHEN** a user with `catalog.manage` creates a unit with no base unit
- **THEN** the client posts a base unit (no conversion factor) and it appears in the list

#### Scenario: Create a derived unit

- **WHEN** a user with `catalog.manage` creates a unit selecting an existing base unit and a
  conversion factor
- **THEN** the client posts a derived unit and it appears showing its base unit and factor

#### Scenario: Backend rejects invalid base/factor combination

- **WHEN** the backend responds with a validation error (e.g. `409`/`422`) for a base/factor mismatch
  or unknown base unit
- **THEN** the UI surfaces the validation message inline and the form remains editable

#### Scenario: Read-only user sees no mutation controls

- **WHEN** a user holding only `catalog.read` views units of measure
- **THEN** create and edit controls are not rendered
