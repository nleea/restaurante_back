# order-management (delta)

## ADDED Requirements

### Requirement: Assign a customer to an open order

The system SHALL allow an authorized user to assign a registered customer to an
**open** order, so the order can later be closed on credit (fiado). The endpoint SHALL
require the order to exist in the tenant and be `open`, and the customer to exist in the
tenant. Assigning to a closed or cancelled order SHALL be rejected. Reassigning while
the order is still open SHALL be allowed. This is the only way a dine-in order (opened
without a customer) becomes fiado-eligible; the fiado close itself is unchanged.

#### Scenario: Assign a customer to an open order

- **WHEN** an authorized user assigns an existing customer to an open order
- **THEN** the order's `customer_id` is set and the updated order is returned

#### Scenario: Fiado becomes possible after assignment

- **WHEN** a customer has been assigned to an open order that has an unpaid remainder
- **AND** the order is then closed
- **THEN** the order closes and the unpaid remainder is recorded as a credit for that customer

#### Scenario: Reject assignment to a non-open order

- **WHEN** a user assigns a customer to an order that is closed or cancelled
- **THEN** the request is rejected and the order is unchanged

#### Scenario: Reject an unknown customer

- **WHEN** a user assigns a customer id that does not exist in the tenant
- **THEN** the request is rejected with a not-found error

#### Scenario: RBAC and tenancy

- **WHEN** a user without `orders.update` attempts to assign a customer
- **THEN** the request is forbidden
- **AND** the order and customer are always resolved within the caller's tenant only
