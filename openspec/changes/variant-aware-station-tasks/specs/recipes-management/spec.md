## ADDED Requirements

### Requirement: A recipe line may fix its kitchen station

A recipe line SHALL accept an optional `station_id` naming the kitchen station where **that
ingredient, in that dish**, is worked. It overrides the ingredient's default station.

The default covers the ordinary case — beef is worked at the grill in every dish that uses it.
The override exists for the ingredient whose station depends on the dish: rice that is boiled in
one plate and fried in another, fish that is grilled in one and battered in another. Without it,
the derivation proposes the wrong station for those dishes every single time.

`station_id`, when given, MUST reference an existing kitchen station of the tenant.

#### Scenario: Set a line's station
- **WHEN** an authorized user sets `station_id` on a recipe line
- **THEN** it is persisted and returned on subsequent reads

#### Scenario: Clear it back to the ingredient's default
- **WHEN** an authorized user sets a line's `station_id` to null
- **THEN** the line falls back to the ingredient's default station

#### Scenario: Reject an unknown station
- **WHEN** a line is saved with a `station_id` that does not exist in the tenant
- **THEN** the system responds 404 Not Found and the line is unchanged

#### Scenario: Deleting a station does not delete recipe lines
- **WHEN** a station referenced by recipe lines is deleted
- **THEN** those lines survive with `station_id` null, falling back to the ingredient's default
