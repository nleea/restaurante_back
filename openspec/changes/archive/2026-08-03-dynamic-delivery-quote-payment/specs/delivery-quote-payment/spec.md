## ADDED Requirements

### Requirement: Branch kilometer tariff plans
The system SHALL let an authorized user configure an active delivery tariff plan per branch as an
ordered set of non-overlapping distance bands. Each band SHALL have a positive upper distance in
kilometers and a non-negative fee; the first band starts at zero and the last upper distance is the
branch's maximum delivery coverage. The system SHALL reject a plan with duplicate, unordered or
gapped bands.

#### Scenario: Configure increasing delivery bands
- **WHEN** a manager saves bands up to 2 km, 4 km and 6 km with their respective fees
- **THEN** the branch has one active plan that selects a fee for every distance from zero through
  6 km

#### Scenario: Reject a plan with a gap
- **WHEN** a manager submits bands that do not continuously cover the interval from zero to their
  maximum distance
- **THEN** the plan is rejected and the previous active plan remains unchanged

### Requirement: Quote a delivery from adjusted geodesic distance
The system SHALL calculate a quote for an open delivery that has final coordinates and whose branch
has an active tariff plan, taking the geodesic distance between the branch location and the
delivery point and adding a fixed 0.7 km pricing buffer. It SHALL select the corresponding band from that adjusted distance,
persist the raw distance, buffer, adjusted distance, band and fee as a quote, add that fee to the
order's authoritative total, and record when the quote was calculated. Distance calculation SHALL
depend on a swappable estimator port so a future road-routing gateway can replace the initial
geodesic-plus-buffer estimator without changing tariff selection or historical quotes.

#### Scenario: Adjusted distance selects its kilometer band
- **WHEN** a delivery is 2.5 km away and the 0.7 km buffer produces 3.2 km, and the active plan
  has bands ending at 2 km and 4 km
- **THEN** the 4 km band's fee is frozen on the delivery and included in the order total

#### Scenario: A future route gateway does not reinterpret quotes
- **WHEN** the branch later switches from the geodesic estimator to a road-routing gateway
- **THEN** existing quotes retain their stored distance, method and fee while new quotes use the
  newly configured estimator

#### Scenario: Distance exceeds coverage
- **WHEN** an adjusted distance is farther than the final band of the active plan
- **THEN** it is marked outside coverage, no delivery fee is added, and no payment request is
  created

### Requirement: Quote processing is asynchronous and retry-safe
The system SHALL calculate quotes outside the order-intake request. A delivery needing a quote
SHALL be retried after a transient geocoding or estimation failure without duplicating a quote, fee
or payment request. A non-resolvable address SHALL remain identifiable for manual correction
instead of receiving an estimated fee.

#### Scenario: Address intake does not wait for a quote
- **WHEN** a customer creates a delivery order from a written address
- **THEN** the order is accepted pending quote and the distance calculation occurs after its
  coordinates are available

#### Scenario: Estimation temporarily fails
- **WHEN** the distance estimator raises while calculating a pending quote
- **THEN** no fee is charged, the delivery remains pending quote, and a later pass can calculate
  it once

### Requirement: An unquotable delivery states why instead of inventing a price
The system SHALL record an actionable failure reason on a delivery it cannot quote, distinguishing
at least a branch without an active tariff plan, a branch without a configured pin, and an address
whose coordinates could not be resolved. It SHALL NOT leave such a delivery indistinguishable from
one that is merely waiting, and SHALL NOT assign it a fee.

#### Scenario: Branch has no tariff plan
- **WHEN** a delivery becomes quotable but its branch has no active tariff plan
- **THEN** the delivery records that reason, keeps a zero fee, and is surfaced for the branch to
  configure its bands rather than being retried silently forever

#### Scenario: Branch pin is missing
- **WHEN** a branch has tariff bands but no configured latitude and longitude
- **THEN** its deliveries record that the origin is unconfigured and no distance is calculated

### Requirement: Quotes are invalidated by a location change
The system SHALL invalidate an unfinalized delivery quote when its address, latitude or longitude
changes. Invalidation SHALL remove the order's previously applied delivery fee, invalidate any
unpaid payment request for that quote, and enqueue a new quote when coordinates are available.

#### Scenario: Customer location is corrected after a quote
- **WHEN** staff correct a quoted delivery's pin before payment verification
- **THEN** the prior fee is removed from the order and the prior payment link cannot be used

### Requirement: Payment requests follow a finalized quote
For a quoted, in-coverage delivery, the system SHALL create an expiring, single-use payment
request containing a secure token scoped only to choosing a payment method and declaring a payment
for that order's current outstanding amount. A request SHALL not create a payment, change its paid
amount, or independently release the order to kitchen. A new quote SHALL invalidate the old
request before a new one can be emitted.

#### Scenario: Customer receives a quote-specific payment request
- **WHEN** a delivery quote is finalized for an order with an outstanding balance
- **THEN** its payment request exposes the frozen delivery fee and current total but cannot edit
  the order or its delivery location

#### Scenario: An old request cannot pay a changed quote
- **WHEN** a delivery has been re-quoted and a customer opens its earlier payment link
- **THEN** the system refuses payment-method selection and payment declaration through that link
