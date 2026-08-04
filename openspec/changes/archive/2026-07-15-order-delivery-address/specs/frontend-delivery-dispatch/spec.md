## MODIFIED Requirements

### Requirement: Manage deliveries

The DispatchView SHALL list deliveries by status and let an authorized user create a delivery for an
open order (selecting the order and capturing a required address, optional neighborhood and optional
notes), and optionally capture the delivery's coordinates by tapping a mini-map (centered on the
branch's business location) or by pasting a shared location (a `lat,lng` pair or a Google Maps
link), with the resolved point shown on the mini-map for confirmation before saving; creation SHALL
require the `delivery.address` permission. A second delivery for the same order SHALL surface a
friendly conflict message. Deliveries SHALL show whether they carry a location, and a delivery
without one (or with a wrong one) SHALL be locatable/correctable later from the board's detail pane
through the same picker.

Address capture is no longer exclusive to the board: the order-taking surfaces capture it too (see
`frontend-salon`). The board's creation flow SHALL remain available as the fallback for orders that
reached dispatch without an address, and SHALL continue to exclude orders that already have a
delivery.

#### Scenario: Create a delivery

- **WHEN** a user with `delivery.address` creates a delivery for an open order with an address
- **THEN** the delivery appears in the list in status `pending`

#### Scenario: Capture the point by tapping the mini-map

- **WHEN** the user taps a point on the form's mini-map before saving
- **THEN** the created delivery carries those coordinates and appears as a dot on the coverage map

#### Scenario: Paste a shared location

- **WHEN** the user pastes a `lat,lng` pair or a Google Maps link from a customer's shared location
- **THEN** the point resolves onto the mini-map for confirmation and is saved with the delivery; an
  unparseable paste explains what formats work instead of failing silently

#### Scenario: Add the location later

- **WHEN** a user with `delivery.address` opens a location-less delivery's detail and picks a point
- **THEN** the delivery is updated with the coordinates and the coverage map's "sin ubicación"
  count decreases

#### Scenario: Duplicate delivery is rejected friendly

- **WHEN** a user creates a delivery for an order that already has one
- **THEN** the screen shows a friendly "ese pedido ya tiene un domicilio" message and no duplicate is
  created

#### Scenario: An order that arrived with its address is not offered for creation

- **WHEN** an order's address was captured at the Salón or the comanda, so it already has a delivery
- **THEN** the board's "Nuevo domicilio" order picker does not offer that order
