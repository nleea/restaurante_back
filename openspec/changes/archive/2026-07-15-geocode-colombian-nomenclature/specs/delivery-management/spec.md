## MODIFIED Requirements

### Requirement: Geocode a delivery address to an approximate pin

The system SHALL provide a geocoder that turns a delivery's written address into an
approximate map location (latitude/longitude) plus, when available, its neighborhood. The
geocoder SHALL be biased to the branch's business location (the delivery-settings pin) and
constrained to the country, so a street resolves within the business's city. Geocoding is
**best-effort**: a failure or no-match SHALL leave the location unset and MUST NOT fail the
operation. The geocoder provider SHALL be configurable (public Nominatim by default) behind
a stable interface, so it can be replaced (e.g. self-hosted) without changing callers.
Results SHOULD be cached so a repeated address does not re-query the provider.

Addresses arrive in Colombian nomenclature (`Calle 41A #12C-48`), whose house number names no
mapped feature. The geocoder SHALL therefore derive the **street** from the address and query
that, while the address SHALL be stored verbatim — the house number is what the driver
delivers by. An address the geocoder cannot parse SHALL be queried as written rather than
rejected, so parsing can only add resolutions over querying the raw text.

The geocoder SHALL **verify** every match: when the provider returns a result whose road does
not name the street that was asked for, that result SHALL be treated as no match. A provider
asked for a street it does not hold may answer with a confident but unrelated match; an
approximate pin is acceptable, a wrong one is not, because nothing downstream can tell them
apart.

When a street carries a letter suffix that yields no verified match, the geocoder SHALL retry
with the base street (`Calle 41A` → `Calle 41`), which the nomenclature defines as adjacent.
It SHALL NOT fall back to the address's cross street: the provider answers with that street's
representative point, which bears no defined relation to the address and has been measured a
full ring band away.

An address with no verified match SHALL yield no location, to be placed by hand.

The resulting pin is **street-level, and no better**: the provider answers with one arbitrary
segment of a street that OSM splits into many ways, so the error is bounded by the street's
length, not by a fixed radius. Measured in Riohacha against the true corner: 90 m for one
address, **3995 m** for another. The house number (`#12C-48`) names the cross street and would
locate the corner, but resolving an intersection is beyond a single-point geocoding query.
Consumers that reason about distance — ring assignment above all — MUST NOT treat this pin as
accurate to better than the street.

#### Scenario: A known street resolves near the business city

- **WHEN** a delivery address naming a street in the branch's city is geocoded
- **THEN** an approximate latitude/longitude on that street (and its neighborhood when
  available) is returned, biased to the business location

#### Scenario: The house number does not prevent a resolution

- **WHEN** an address in Colombian nomenclature such as `Calle 15 #10-20` is geocoded
- **THEN** the street is queried without the house number and resolves, and the stored address
  keeps the house number unchanged

#### Scenario: A match on a different road is rejected

- **WHEN** the provider answers a request for one street with a result whose road is another
  street
- **THEN** the geocoder treats it as no match and returns no location

#### Scenario: A letter-suffixed street falls back to its base street

- **WHEN** `Calle 41A` yields no verified match
- **THEN** the geocoder retries `Calle 41` and returns that location when it verifies

#### Scenario: The cross street is never used as a fallback

- **WHEN** neither `Calle 41A` nor `Calle 41` verifies for `Calle 41A #12C-48`
- **THEN** the geocoder returns no location, and does not resolve to Carrera 12C

#### Scenario: An unparseable address is still attempted

- **WHEN** an address does not match the nomenclature the parser knows
- **THEN** it is queried as written, and geocoding neither raises nor blocks the operation

#### Scenario: An unresolvable address yields no location

- **WHEN** the address cannot be matched
- **THEN** the geocoder returns no location and the caller proceeds with an unset pin

#### Scenario: Editing an address re-geocodes when no explicit pin is given

- **WHEN** a delivery's address is edited and no explicit pin is provided
- **THEN** the location is re-derived from the new address (best-effort), and an explicitly
  provided pin is preserved instead
