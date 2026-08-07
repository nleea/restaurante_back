# frontend-delivery (delta)

## ADDED Requirements

### Requirement: Live deliveries overlay

The coverage map SHALL plot the open per-order deliveries (`pending`, `assigned`, `in_transit`)
that carry coordinates as dots colored by status, each with a tooltip showing the address and
status. A "Pedidos (N)" toggle on the map SHALL show/hide the overlay (on by default) carrying
the live plotted count, and open deliveries without coordinates SHALL be surfaced as a count
("N sin ubicación") rather than silently omitted. The overlay is read-only — assignment and
lifecycle actions stay on the dispatch screen — and refreshes with the screen's load/refresh
actions.

#### Scenario: Open deliveries appear as status dots

- **WHEN** the branch has open deliveries with coordinates
- **THEN** the map shows one dot per delivery, colored by its status, with address + status on
  hover

#### Scenario: Delivered orders leave the map

- **WHEN** a delivery reaches `delivered` or `not_delivered` and the screen refreshes
- **THEN** its dot is no longer plotted and the toggle count decreases

#### Scenario: Unlocated deliveries are counted, not hidden

- **WHEN** open deliveries exist without coordinates
- **THEN** the map shows a "N sin ubicación" note next to the toggle

#### Scenario: Overlay toggle

- **WHEN** the user turns the "Pedidos" toggle off
- **THEN** the dots hide instantly and reappear when toggled back on
