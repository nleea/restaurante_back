# catalog-management

## Purpose

Global reference catalogs shared across all tenants: countries, cities, and units
of measure. Gives `units_of_measure` (already consumed by recipes/purchasing) a
real API and a home for the geographic catalogs. Data is NOT tenant-scoped;
RBAC still applies.

Out of scope for this capability: restricting writes to a platform-admin tier
(no such tier exists in RBAC yet), unit-conversion math (only stores
`base_unit_id`/`conversion_factor`), and bulk seeding of standard catalogs.

## Requirements

### Requirement: Global catalogs with RBAC

The catalog tables (countries, cities, units of measure) are global reference data shared across tenants and are NOT tenant-scoped. The system SHALL still require an authenticated request and SHALL enforce RBAC: `catalog.read` for reads and `catalog.manage` for writes. These permissions SHALL be present in the permissions catalog.

#### Scenario: Read without permission
- **WHEN** a user lacking `catalog.read` calls a catalog read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Write without permission
- **WHEN** a user lacking `catalog.manage` tries to create a country, city or unit
- **THEN** the system responds 403 Forbidden

#### Scenario: Catalog data is shared across tenants
- **WHEN** an authorized user in any tenant lists units of measure
- **THEN** the global units are returned regardless of tenant

### Requirement: Manage countries

The system SHALL allow authorized users to create, list, retrieve and update countries (name and a unique ISO code).

#### Scenario: Create a country
- **WHEN** an authorized user creates a country with a name and an unused ISO code
- **THEN** the country is persisted and returned

#### Scenario: Reject duplicate ISO code
- **WHEN** a user creates a country with an ISO code that already exists
- **THEN** the system responds with a conflict error

### Requirement: Manage cities

The system SHALL allow authorized users to create, list, retrieve and update cities tied to a country (name, optional state/province), and to list cities by country. The `country_id` MUST reference an existing country.

#### Scenario: Create a city
- **WHEN** an authorized user creates a city under an existing country
- **THEN** the city is persisted and returned

#### Scenario: Reject unknown country
- **WHEN** a user creates a city referencing a `country_id` that does not exist
- **THEN** the system responds 404 Not Found

#### Scenario: List cities by country
- **WHEN** an authorized user lists cities for a country
- **THEN** only that country's cities are returned

### Requirement: Manage units of measure

The system SHALL allow authorized users to create, list, retrieve and update units of measure (name, abbreviation, optional `base_unit_id` and `conversion_factor`). When a `base_unit_id` is provided it MUST reference an existing unit and a positive `conversion_factor` MUST be provided; `base_unit_id` and `conversion_factor` MUST be set together or both omitted. A unit MUST NOT be its own base unit.

#### Scenario: Create a base unit
- **WHEN** an authorized user creates a unit with no base unit
- **THEN** the unit is persisted as a base unit (no conversion factor)

#### Scenario: Create a derived unit
- **WHEN** an authorized user creates a unit with an existing `base_unit_id` and a positive `conversion_factor`
- **THEN** the unit is persisted with its conversion toward the base

#### Scenario: Reject base/factor mismatch
- **WHEN** a user provides a `base_unit_id` without a `conversion_factor` (or vice versa), or a non-positive factor
- **THEN** the system responds with a validation error

#### Scenario: Reject unknown base unit
- **WHEN** a user provides a `base_unit_id` that does not exist
- **THEN** the system responds 404 Not Found

#### Scenario: Reject self-referential base unit
- **WHEN** a user updates a unit to set its own id as `base_unit_id`
- **THEN** the system responds with a validation error
