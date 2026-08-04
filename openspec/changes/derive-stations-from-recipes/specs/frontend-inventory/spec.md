## ADDED Requirements

### Requirement: Assign a default kitchen station to an insumo

The inventory board's insumo editor SHALL let an authorized user pick the kitchen station where
that insumo is worked, and clear it again. The station is optional: an insumo without one stays
fully usable, it simply contributes nothing to the kitchen's station derivation.

The selector SHALL be presented as a mono two-letter station tag consistent with the KDS station
rail — colour stays reserved for heat and state — and SHALL be driven by the active branch's
stations loaded from the database, never a hardcoded list.

#### Scenario: Set an insumo's station
- **WHEN** an authorized user picks a station in the insumo editor and saves
- **THEN** the client sends `default_station_id` on the ingredient update and the tag is shown on
  the insumo afterwards

#### Scenario: Clear an insumo's station
- **WHEN** an authorized user removes the station from an insumo and saves
- **THEN** the client sends `default_station_id` as null and the tag disappears

#### Scenario: No stations configured yet
- **WHEN** the active branch has no kitchen stations
- **THEN** the selector is shown empty with a hint pointing to kitchen configuración, and saving
  the insumo without a station still succeeds

#### Scenario: Permission gate
- **WHEN** a user without the permission that governs insumo editing opens the board
- **THEN** the station selector is not offered, consistent with the rest of the editor
