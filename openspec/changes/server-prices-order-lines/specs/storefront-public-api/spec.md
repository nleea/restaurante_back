## MODIFIED Requirements

### Requirement: Public order intake

`POST /storefront/orders` SHALL create a real order from a customer cart without authentication,
scoped to the subdomain tenant. It SHALL require a customer name and phone, find-or-create the
customer by phone, open an order on the tenant's system employee with channel `takeaway` (pickup) or
`delivery`, record the customer's chosen payment method as an intent on the order
(`orders.payment_method`), add each cart line with its selected addons and a kitchen note (chosen
ingredient removals folded into the note), and, for delivery, attach a delivery with the given
address / coordinates. It SHALL return an order identifier/number and the initial status. The order
SHALL be created unpaid and left **pending staff confirmation** — its items SHALL NOT auto-fire to
the kitchen; staff confirm and fire them (a delivery order still enters Dispatch as pending). No
`order_payments` row is created at intake (that models money actually received).

The cart SHALL NOT carry prices, and intake SHALL NOT resolve them on its own: each line's price comes
from the system's single resolution, which includes the variant's surcharge. This closes a divergence
in which the public channel charged the product's branch price while the staff channel added the
surcharge on top.

Intake SHALL refuse a line whose product has no price for the order's branch, rather than creating it
at zero.

#### Scenario: Pickup order is created

- **WHEN** an unauthenticated customer submits a pickup cart with valid line items
- **THEN** the system creates a `takeaway` order with those items and addons and returns an order
  number with an initial (open/pending) status

#### Scenario: A cart cannot name its own prices

- **WHEN** a cart is submitted
- **THEN** every line is priced by the system, and any price present in the payload has no effect on
  what is charged

#### Scenario: The public channel charges the variant surcharge

- **WHEN** a public order is placed for a variant carrying a surcharge
- **THEN** the line is charged the branch price plus that surcharge — the same amount staff would
  charge for it

#### Scenario: An unpriced product is refused, not given away

- **WHEN** a cart contains a product with no price for that branch
- **THEN** intake is refused and no order line is created at zero

#### Scenario: Order lands pending, not auto-fired

- **WHEN** a storefront order is created
- **THEN** its items are pending (not routed to the kitchen) and become visible for staff to confirm
  and fire, exactly like a not-yet-fired staff order
