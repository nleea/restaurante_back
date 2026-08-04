## MODIFIED Requirements

### Requirement: Verifying a prepaid payment is one action in Salón

For an unrouted order whose payment method is not cash, Salón SHALL present a verification action
stating what to check (the transfer receipt or the payment app) and how much. Confirming it SHALL
register the payment and send the order to the kitchen in a single step, and SHALL report clearly
if it could not be completed.

When **no** pending claim on that order carries a receipt and the order is linked to a WhatsApp
contact, the verification block SHALL offer a way into that contact's conversation. A customer who
says they paid and attaches nothing has almost always sent the proof to the chat — the bank offers
to share to WhatsApp the moment the transfer completes — so that is where the person verifying has
to look.

Once any pending claim carries a receipt, the shortcut SHALL NOT be offered: the image is already
in front of them and a second route to it is noise.

#### Scenario: Verification pays and fires in one step

- **WHEN** staff confirm the payment of a prepaid order
- **THEN** the order shows as paid and sent to the kitchen

#### Scenario: An unverified prepaid order cannot be sent to the kitchen

- **WHEN** staff try to send an unverified prepaid order to the kitchen
- **THEN** the action is unavailable or refused, explaining that the payment must be verified first

#### Scenario: A cash order is sent without verification

- **WHEN** staff open a cash order
- **THEN** it can be sent to the kitchen with no verification step
- **AND** it states that the customer pays cash on arrival, so the decision to cook is informed

#### Scenario: A delivery with no method chosen yet says so

- **WHEN** staff open a delivery order whose customer has not chosen how to pay
- **THEN** it says the choice is still pending and where the customer makes it, instead of
  looking identical to a cash order

#### Scenario: A claim with no receipt points to the chat

- **WHEN** staff open an order whose only pending claim has no receipt, and whose customer is a linked WhatsApp contact
- **THEN** the verification block offers to open that contact's conversation

#### Scenario: No claim at all still points to the chat

- **WHEN** staff open a prepaid order with no pending claim, and whose customer is a linked WhatsApp contact
- **THEN** the verification block offers to open that contact's conversation

#### Scenario: An attached receipt hides the shortcut

- **WHEN** staff open an order with a pending claim that carries a receipt
- **THEN** the receipt is shown and no shortcut to the conversation is offered

#### Scenario: An order with no WhatsApp contact offers no shortcut

- **WHEN** staff open a prepaid order with no receipt and no linked WhatsApp contact
- **THEN** no shortcut to a conversation is offered
