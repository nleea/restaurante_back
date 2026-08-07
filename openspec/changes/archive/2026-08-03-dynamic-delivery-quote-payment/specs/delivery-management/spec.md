## ADDED Requirements

### Requirement: Delivery location changes coordinate with quoting
The delivery module SHALL expose the quote status of each delivery and SHALL notify the quote
workflow when a delivery record gains coordinates or when its address or coordinates change. An
explicit or hand-placed pin remains authoritative for location; quote calculation consumes it but
does not overwrite it.

#### Scenario: Background geocoding makes a delivery quotable
- **WHEN** the geocoding worker persists coordinates for a pending delivery
- **THEN** the delivery becomes eligible for asynchronous distance quotation

#### Scenario: Manual pin replaces an unresolved address
- **WHEN** an operator places a pin for a delivery whose address could not be resolved
- **THEN** the pin is retained as the delivery location and a quote can be calculated from it
