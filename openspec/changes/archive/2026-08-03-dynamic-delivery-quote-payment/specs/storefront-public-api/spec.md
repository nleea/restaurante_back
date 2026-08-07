## ADDED Requirements

### Requirement: Public delivery intake defers price and payment method
The public storefront API SHALL accept a delivery order containing customer contact, products and
location without a payment-method selection. It SHALL create the order and delivery record pending
quote, return a response that does not claim a final payable total, and preserve the provided GPS
coordinates when present.

#### Scenario: Customer submits address without choosing payment
- **WHEN** a customer submits a delivery order with a written address and no payment method
- **THEN** the API creates the order successfully and returns that its delivery value will be
  confirmed later

#### Scenario: Customer submits a GPS point
- **WHEN** a customer submits a delivery order with latitude and longitude
- **THEN** those coordinates are stored for later quotation without waiting for a quote result

### Requirement: A payment request endpoint has narrow authority
The public API SHALL expose a token-authenticated payment-request surface that shows the current
quoted amount, lets the customer select a supported payment method, and lets them declare/send a
payment proof. It SHALL reject expired, consumed or invalidated tokens and SHALL NOT expose order
editing or another customer's information.

#### Scenario: Customer chooses transfer from a valid request
- **WHEN** a customer opens a valid payment request and selects transfer
- **THEN** the order records transfer as an intent and the customer can declare a payment with its
  current outstanding amount

#### Scenario: Expired request reveals no payment action
- **WHEN** a customer opens an expired payment request token
- **THEN** the API refuses the request and exposes no ability to change payment intent or submit a
  proof
