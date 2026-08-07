## ADDED Requirements

### Requirement: Persist the appearance config per tenant

The system SHALL store one public-carta appearance config per tenant as a single JSONB document
in a tenant-scoped `menu_appearance` table. The stored document MUST be the whole
`MenuAppearanceConfig` (theme, brand, blocks, dishCard, dishDetail, blockContent) so the shape the
admin edits equals the shape the storefront reads. Saving SHALL upsert (create on first save,
overwrite thereafter), keeping at most one row per tenant.

#### Scenario: First save creates the row

- **WHEN** an authorized user PUTs an appearance config for a tenant that has none
- **THEN** the system inserts one `menu_appearance` row for that tenant and returns the saved config

#### Scenario: Subsequent save overwrites

- **WHEN** an authorized user PUTs an appearance config for a tenant that already has one
- **THEN** the system overwrites the existing row (still one row) and returns the saved config

#### Scenario: Tenant isolation

- **WHEN** two tenants each save an appearance config
- **THEN** each tenant reads back only its own config, never the other's

### Requirement: Read the appearance config with a default fallback

`GET /menu/appearance` SHALL return the tenant's saved config, or a sensible default config when
the tenant has never saved one, so the editor and storefront always receive a usable document
(never a 404 for "not configured yet").

#### Scenario: Read a saved config

- **WHEN** the tenant has a saved appearance config and an authorized user reads it
- **THEN** the system returns that exact config

#### Scenario: Read before any save returns a default

- **WHEN** the tenant has never saved a config and an authorized user reads it
- **THEN** the system returns a valid default config (default theme, brand, and block layout)

### Requirement: RBAC protection of the appearance endpoints

Reading the appearance config SHALL require `menu.read`; writing it SHALL require `menu.manage`.
These are enforced server-side independent of any client-side gating.

#### Scenario: Read without permission is rejected

- **WHEN** a user without `menu.read` calls `GET /menu/appearance`
- **THEN** the system responds 403 Forbidden

#### Scenario: Write without permission is rejected

- **WHEN** a user without `menu.manage` calls `PUT /menu/appearance`
- **THEN** the system responds 403 Forbidden and no config is written

### Requirement: Validate the appearance config on write

`PUT /menu/appearance` SHALL validate the incoming document against the appearance config schema
and reject malformed payloads, so a persisted config always has the fields the editor and
storefront rely on.

#### Scenario: Reject a malformed config

- **WHEN** an authorized user PUTs a payload missing required config sections or with wrong types
- **THEN** the system responds 422 Unprocessable Entity and does not persist the payload
