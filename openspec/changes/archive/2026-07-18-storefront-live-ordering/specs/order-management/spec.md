## ADDED Requirements

### Requirement: Order payment-method intent

The system SHALL support a nullable `payment_method` on an order that records a customer's chosen
payment method as an intent, distinct from an actual `order_payments` record (which represents money
received into a cash session). Setting the intent SHALL NOT register a payment, affect paid totals,
or gate closing.

#### Scenario: Intent is recorded without a payment

- **WHEN** an order is created with a `payment_method` intent
- **THEN** the order stores that method, its paid total remains zero, and no `order_payments` row
  exists until a real payment is registered

#### Scenario: Intent is optional

- **WHEN** an order is created without a `payment_method`
- **THEN** the field is null and order behavior is unchanged
