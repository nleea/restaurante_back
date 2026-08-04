## ADDED Requirements

### Requirement: Auto-route new items to the kitchen

When an item is added to an open order, the system SHALL route the order to the kitchen, creating a
ticket for each routable item (one whose product is mapped to a kitchen station). Routing SHALL be
idempotent — an item already ticketed at a station SHALL NOT be ticketed again — and SHALL be a no-op
when the kitchen is not configured (no stations or product→station mappings yield no tickets).
Routing SHALL be best-effort and non-blocking: a routing failure SHALL NOT prevent the item from
being added, and the manual route remains available as a fallback.

#### Scenario: Adding a mapped item creates its kitchen ticket

- **WHEN** an item whose product is mapped to a kitchen station is added to an open order
- **THEN** the item is added
- **AND** a kitchen ticket for that item at the mapped station exists (status `pending`)

#### Scenario: Adding an unmapped item creates no ticket

- **WHEN** an item whose product has no station mapping is added to an open order
- **THEN** the item is added
- **AND** no kitchen ticket is created for it

#### Scenario: Auto-routing is idempotent

- **WHEN** an order is routed automatically more than once (e.g. as further items are added)
- **THEN** items already ticketed at a station are not ticketed again
- **AND** only newly added routable items receive tickets

#### Scenario: A routing failure does not block the item add

- **WHEN** kitchen routing fails while an item is being added
- **THEN** the item is still added to the order
