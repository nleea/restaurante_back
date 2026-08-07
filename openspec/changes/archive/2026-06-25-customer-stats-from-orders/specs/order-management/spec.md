## ADDED Requirements

### Requirement: Update customer stats on close

When an order with a linked `customer_id` is closed, the system SHALL update that customer's purchase
stats in the same operation as the close: increment `order_count` by one, add the order `total` to
`total_spent`, and set `last_purchase_at` to the close time. An order with no linked customer SHALL
leave all customer stats untouched. The update SHALL occur exactly once per order — because a closed
order cannot be closed again, an order's stats SHALL NOT be counted twice.

#### Scenario: Closing an order updates the linked customer's stats

- **WHEN** an order with a linked customer and a known total is closed
- **THEN** the customer's `order_count` increases by one
- **AND** the order's total is added to the customer's `total_spent`
- **AND** the customer's `last_purchase_at` is set to the close time

#### Scenario: An order without a customer leaves stats untouched

- **WHEN** an order with no `customer_id` is closed
- **THEN** no customer's stats are changed

#### Scenario: Stats are not double-counted

- **WHEN** an order has already been closed and its customer's stats updated
- **THEN** the order cannot be closed again
- **AND** the customer's stats are not incremented a second time
