# frontend-delivery (delta)

## MODIFIED Requirements

### Requirement: Live deliveries overlay

The deliveries overlay SHALL paint each order's pin from its stored `latitude`/`longitude`.
Those coordinates are geocoded server-side from the address (the frontend does not
geocode). When an order has no pin (geocoding did not resolve its address), the overlay
SHALL make it clear the location is unset and SHALL let an operator place it with the manual
map picker; an approximate pin MAY be dragged to correct it. A manually placed pin is
authoritative and is not re-derived by geocoding.

#### Scenario: A geocoded order is painted on the map

- **WHEN** a delivery order has server-derived coordinates
- **THEN** its pin is painted at that approximate location on the map

#### Scenario: An order without a pin can be placed manually

- **WHEN** a delivery order has no coordinates
- **THEN** the overlay surfaces that its location is unset and the operator can place it with
  the manual picker

#### Scenario: Correcting an approximate pin

- **WHEN** an operator adjusts an order's pin with the manual picker
- **THEN** the corrected location is saved and treated as authoritative
