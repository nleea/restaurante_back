## ADDED Requirements

### Requirement: An unsettled prepaid order never says it is being prepared

Every customer-facing view SHALL state that the payment is being awaited, and that the order is held
until the receipt is seen, when the order was placed with a non-cash method and has no payment
registered — and SHALL NOT present such an order as being prepared. When a receipt is already pending review, the
views SHALL say that instead, so the customer is not asked twice for something already sent.

The same fact SHALL be worded from one shared place, so the checkout's confirmation and the "my
order" view cannot drift apart.

Saying "being prepared" about an order the kitchen has not seen is not a wording detail: it produces
the "is it ready yet?" question and the disappointment at the door.

#### Scenario: The confirmation states what is missing

- **WHEN** a customer confirms an order by transfer without attaching a receipt
- **THEN** the confirmation states that the payment is awaited, that the order is held, and that it
  enters the kitchen once the receipt is seen

#### Scenario: "My order" says the same thing

- **WHEN** that customer opens their order later
- **THEN** it states the same, not "being prepared"

#### Scenario: A receipt under review is distinguished

- **WHEN** the customer has already sent a receipt and it is pending
- **THEN** the views say the receipt is being reviewed, rather than asking for it again

#### Scenario: Cash and settled orders are unaffected

- **WHEN** the order is to be paid in cash, or is already settled
- **THEN** the status shown is the one shown today

## MODIFIED Requirements

### Requirement: Sending the receipt by WhatsApp is offered alongside attaching it

The view SHALL offer sending the receipt through the business's WhatsApp as an alternative to
attaching it, whenever the branch has a reachable number. Neither path SHALL be presented as
making the payment confirmed.

The WhatsApp route SHALL open the chat with a message already written, carrying the order's number
and total. Without them, the arriving file is a photograph with no context and whoever attends the
number cannot tell which order it pays or how much was owed — which is the whole reason the route
exists.

This also keeps the channel's outbound invariant intact: the customer is the one who writes first, so
nothing here initiates a conversation.

#### Scenario: Both routes are offered

- **WHEN** a customer must send a receipt
- **THEN** the view offers to attach it and to send it by WhatsApp

#### Scenario: WhatsApp remains available when the upload fails

- **WHEN** the attachment cannot be uploaded
- **THEN** the WhatsApp route is still offered

#### Scenario: No number, no dead button

- **WHEN** the branch has no phone
- **THEN** the WhatsApp route is not offered and attaching still is

#### Scenario: The chat opens with the order written in

- **WHEN** the customer takes the WhatsApp route
- **THEN** the chat opens with a message containing the order's number and total, ready to send
