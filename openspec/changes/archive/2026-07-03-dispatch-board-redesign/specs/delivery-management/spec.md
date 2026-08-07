# delivery-management (delta)

## ADDED Requirements

### Requirement: Delivery record timestamps and notes

The system SHALL persist `created_at` and `updated_at` timestamps on per-order delivery records and
SHALL expose `created_at` on the delivery read model and on the dispatch-run read model. Delivery
records SHALL support an optional free-text `notes` field (≤ 500 characters), editable through the
existing delivery update endpoint under the `delivery.manage` permission.

#### Scenario: Delivery exposes its creation time

- **WHEN** an authorized user creates a delivery and then reads it
- **THEN** the response includes a `created_at` timestamp set at creation time

#### Scenario: Run exposes its creation time

- **WHEN** an authorized user reads a dispatch run
- **THEN** the response includes the run's `created_at` timestamp

#### Scenario: Update delivery notes

- **WHEN** a user with `delivery.manage` patches a delivery with `notes`
- **THEN** the notes are persisted and returned on subsequent reads

#### Scenario: Overlong notes are rejected

- **WHEN** a user patches a delivery with notes longer than 500 characters
- **THEN** the system responds with a validation error and the delivery is unchanged
