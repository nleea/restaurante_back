## MODIFIED Requirements

### Requirement: Geocode a delivery address to an approximate pin

The system SHALL provide a geocoder that turns a delivery's written address into an
approximate map location (latitude/longitude) plus, when available, its neighborhood. The
geocoder SHALL be biased to the branch's business location (the delivery-settings pin) and
constrained to the country, so a street resolves within the business's city. Geocoding is
**best-effort**: a failure or no-match SHALL leave the location unset and MUST NOT fail the
operation. The geocoder providers SHALL be configurable behind a stable interface, so they can
be replaced (e.g. self-hosted) without changing callers. Results SHOULD be cached so a repeated
address does not re-query the provider.

Addresses arrive in Colombian nomenclature (`Calle 41A #12C-48`), which names **two** streets —
the street and the cross street — whose crossing is the address's corner. The house number
names no mapped feature. The geocoder SHALL therefore derive both streets from the address and
resolve **their intersection**, while the address SHALL be stored verbatim — the house number
is what the driver delivers by. An address the geocoder cannot parse SHALL be queried as
written rather than rejected.

When the intersection cannot be resolved — either street missing from the map data, or an
address naming only one street — the geocoder SHALL fall back to resolving the street alone.
A street-only pin SHALL be understood as accurate only to the street: map data splits a street
into many segments and a single-point query answers with an arbitrary one, so the error is
bounded by the street's length. Measured in Riohacha: a street-only pin landed **27 m** from
the wrong corner (`Carrera 10`) for an address on `Carrera 12C` **555 m** away, and **3995 m**
from the true corner for another address. The intersection is therefore preferred wherever it
resolves, and consumers that reason about distance — ring assignment above all — SHALL treat a
street-only pin as no better than street-accurate.

The geocoder SHALL **verify** every street match: a result whose road does not name the street
that was asked for SHALL be treated as no match. When a street carries a letter suffix that
yields no match, the geocoder SHALL retry with the base street (`Calle 41A` → `Calle 41`), for
the intersection as well as for the street-only fallback. It SHALL NOT resolve to the cross
street alone: that street's own point bears no defined relation to the address and has been
measured a full ring band away.

An address with no verified match SHALL yield no location, to be placed by hand.

Geocoding SHALL NOT run inside creating or updating a delivery record: those operations SHALL
store the address and return, leaving the pin to be resolved afterwards (see the
`delivery-geocoding-worker` capability). Editing an address without giving an explicit pin
SHALL clear the stored pin, so the record is resolved again from its new address. An explicitly
provided pin SHALL always be preserved and never re-derived.

#### Scenario: The address's corner is resolved

- **WHEN** an address naming a street and a cross street both present in the map data is
  geocoded
- **THEN** the location returned is their intersection, not a point on either street

#### Scenario: A letter-suffixed street still finds its corner

- **WHEN** `Calle 41A #12C-48` is geocoded and the map data holds `Calle 41` but not `Calle 41A`
- **THEN** the intersection of `Calle 41` and `Carrera 12C` is returned

#### Scenario: No resolvable intersection falls back to the street

- **WHEN** the intersection of the two streets cannot be resolved
- **THEN** the street alone is resolved and returned, and the pin is understood as
  street-accurate only

#### Scenario: The house number does not prevent a resolution

- **WHEN** an address in Colombian nomenclature such as `Calle 15 #10-20` is geocoded
- **THEN** the streets are queried without the house number, and the stored address keeps the
  house number unchanged

#### Scenario: A match on a different road is rejected

- **WHEN** the provider answers a request for one street with a result whose road is another
  street
- **THEN** the geocoder treats it as no match and returns no location

#### Scenario: The cross street is never resolved on its own

- **WHEN** no intersection and no street verifies for `Calle 41A #12C-48`
- **THEN** the geocoder returns no location, and does not resolve to Carrera 12C

#### Scenario: An unparseable address is still attempted

- **WHEN** an address does not match the nomenclature the parser knows
- **THEN** it is queried as written, and geocoding neither raises nor blocks the operation

#### Scenario: Creating a delivery does not wait for a pin

- **WHEN** a delivery record is created with an address
- **THEN** the record is stored immediately with no location, and the caller is not blocked by
  any geocoding provider

#### Scenario: Editing an address queues it for re-resolution

- **WHEN** a delivery's address is edited and no explicit pin is provided
- **THEN** the stored pin is cleared so the record is resolved again from the new address

#### Scenario: An explicit pin is preserved

- **WHEN** a delivery carries an explicitly provided pin
- **THEN** that pin is kept as-is and is never re-derived from the address

#### Scenario: An unresolvable address yields no location

- **WHEN** the address cannot be matched
- **THEN** the geocoder returns no location and the caller proceeds with an unset pin
