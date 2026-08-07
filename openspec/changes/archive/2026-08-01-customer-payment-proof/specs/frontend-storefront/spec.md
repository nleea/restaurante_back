## ADDED Requirements

### Requirement: The checkout's receipt attachment actually sends the receipt

When the chosen payment method asks for proof, the storefront SHALL upload the attached file and
submit it with the order. It SHALL NOT present an attachment control that discards the file.

#### Scenario: The attached receipt reaches the order

- **WHEN** a customer attaches a receipt and places the order
- **THEN** the order is created carrying that receipt

#### Scenario: A failed upload is not silently swallowed

- **WHEN** the receipt cannot be uploaded
- **THEN** the customer is told, and can retry or continue without it rather than believing it was sent

### Requirement: «Mi pedido» offers to settle the difference

The view SHALL offer the same payment step the checkout uses — method and receipt — when an edit
raises what the customer owes and their method is one paid in advance, instead of only pointing
at a person.

The view SHALL present the amount **still owed**, never the order's full total, and SHALL state
that the restaurant confirms the payment.

#### Scenario: Paying the difference is reachable from the order

- **WHEN** an edit leaves an outstanding amount on a prepaid order
- **THEN** the view offers to send the receipt for what is missing

#### Scenario: The figure shown is what is missing

- **WHEN** a customer who already paid 40.000 owes 2.500 more
- **THEN** the view shows 2.500 as the amount to send, not 42.500

#### Scenario: A sent receipt is reported as pending, not as paid

- **WHEN** the customer sends the receipt
- **THEN** the view says it is awaiting the restaurant's confirmation and still shows the amount as owed

#### Scenario: Cash orders are not asked for a receipt

- **WHEN** the order is paid on delivery
- **THEN** the view says it is paid on arrival and offers no upload

### Requirement: Sending the receipt by WhatsApp is offered alongside attaching it

The view SHALL offer sending the receipt through the business's WhatsApp as an alternative to
attaching it, whenever the branch has a reachable number. Neither path SHALL be presented as
making the payment confirmed.

#### Scenario: Both routes are offered

- **WHEN** a customer must send a receipt
- **THEN** the view offers to attach it and to send it by WhatsApp

#### Scenario: WhatsApp remains available when the upload fails

- **WHEN** the attachment cannot be uploaded
- **THEN** the WhatsApp route is still offered

#### Scenario: No number, no dead button

- **WHEN** the branch has no phone
- **THEN** the WhatsApp route is not offered and attaching still is
