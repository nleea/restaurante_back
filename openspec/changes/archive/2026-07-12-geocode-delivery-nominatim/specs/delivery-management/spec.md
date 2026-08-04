# delivery-management (delta)

## ADDED Requirements

### Requirement: Geocode a delivery address to an approximate pin

The system SHALL provide a geocoder that turns a delivery's written address into an
approximate map location (latitude/longitude) plus, when available, its neighborhood. The
geocoder SHALL be biased to the branch's business location (the delivery-settings pin) and
constrained to the country, so a street resolves within the business's city. Geocoding is
**best-effort**: a failure or no-match SHALL leave the location unset and MUST NOT fail the
operation. The geocoder provider SHALL be configurable (public Nominatim by default) behind
a stable interface, so it can be replaced (e.g. self-hosted) without changing callers.
Results SHOULD be cached so a repeated address does not re-query the provider.

#### Scenario: A known street resolves near the business city

- **WHEN** a delivery address naming a street in the branch's city is geocoded
- **THEN** an approximate latitude/longitude on that street (and its neighborhood when
  available) is returned, biased to the business location

#### Scenario: An unresolvable address yields no location

- **WHEN** the address cannot be matched
- **THEN** the geocoder returns no location and the caller proceeds with an unset pin

#### Scenario: Editing an address re-geocodes when no explicit pin is given

- **WHEN** a delivery's address is edited and no explicit pin is provided
- **THEN** the location is re-derived from the new address (best-effort), and an explicitly
  provided pin is preserved instead

## MODIFIED Requirements

### Requirement: Create a per-order delivery record

The system SHALL create a per-order delivery record from an order, its address text, and an
optional neighborhood and pin. When **no explicit pin** is provided and an address is
present, the system SHALL geocode the address (best-effort, biased to the branch business
location) and store the resulting latitude/longitude, filling the neighborhood when it was
not given. An explicitly provided pin SHALL always be kept as-is and never overwritten by
geocoding. A geocoding failure SHALL NOT prevent the delivery record from being created.

#### Scenario: Create with only an address geocodes a pin

- **WHEN** a delivery record is created with an address but no pin
- **THEN** the record is created and, if the address resolves, its latitude/longitude are
  set from geocoding (and the neighborhood filled when empty)

#### Scenario: An explicit pin is preserved

- **WHEN** a delivery record is created with an explicit pin
- **THEN** that pin is stored unchanged and no geocoding overwrites it

#### Scenario: Geocoding failure still creates the record

- **WHEN** the address cannot be geocoded
- **THEN** the delivery record is still created, with an unset pin to be placed manually
