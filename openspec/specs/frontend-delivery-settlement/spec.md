# frontend-delivery-settlement

## Purpose

Las pantallas del cierre de un domicilio: entregas bloqueadas en Despacho con su motivo, el
"confirmar y cerrar" del domiciliario, la verificación de pago en Salón, el cierre de caja
bloqueado, y las devoluciones pendientes.

El hilo común es no dejar controles muertos: un botón deshabilitado sin explicación se lee
como una app rota, y un error genérico donde había un motivo concreto convierte una acción
en un callejón.

## Requirements
### Requirement: Dispatch shows unready deliveries as blocked, not hidden

The dispatch board SHALL list deliveries whose order is not yet ready alongside the rest, visibly
blocked and stating that the kitchen has not finished. The assign action SHALL be unavailable for
them. They SHALL NOT be hidden: a dispatcher needs to see what is coming in order to plan a run.

#### Scenario: An unready delivery is visible and blocked

- **WHEN** the dispatcher opens the board with a delivery whose order is still in the kitchen
- **THEN** the delivery is listed, marked as not ready, and cannot be assigned

#### Scenario: The block explains itself

- **WHEN** a dispatcher looks at a blocked delivery
- **THEN** the reason shown is that the kitchen has not finished, not a generic disabled control

#### Scenario: A delivery becomes assignable when the kitchen finishes

- **WHEN** the last kitchen ticket of that order is marked ready
- **THEN** the delivery stops being blocked without the dispatcher reloading

### Requirement: The courier collects cash and closes in one action

For a cash delivery, the driver view SHALL show the amount to collect and offer a single action
that confirms the money and settles the delivery. For an already-paid delivery it SHALL offer a
plain delivered action and SHALL NOT ask for money.

#### Scenario: A cash stop asks for the exact amount

- **WHEN** the courier opens a cash delivery
- **THEN** the amount to collect is shown, and the action confirms the money and the delivery
  together

#### Scenario: A prepaid stop does not ask for money

- **WHEN** the courier opens an already-paid delivery
- **THEN** no amount is requested and the action only marks it delivered

#### Scenario: A failed collection says so

- **WHEN** confirming a collection fails
- **THEN** the courier is told, and the stop is still shown as pending rather than as delivered

### Requirement: A delivered order stops asking to be charged

Once a delivery is settled and its order closed, the order SHALL disappear from the screens that
list orders pending collection.

#### Scenario: A delivered order leaves the pending-collection list

- **WHEN** a delivery is marked delivered and its order closes
- **THEN** the order no longer appears in Salón as pending collection

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

### Requirement: The cash close names what is blocking it

When closing a cash session is refused because deliveries are unresolved, the front SHALL list
those deliveries and offer a way to reach them, rather than reporting a generic error. It SHALL
NOT offer a way to close anyway.

#### Scenario: The blocked close lists the offenders

- **WHEN** a cashier tries to close a session with unresolved deliveries
- **THEN** those deliveries are listed with their state and a way to open them

#### Scenario: No override is offered

- **WHEN** the close is blocked
- **THEN** no control is shown that closes the session regardless

#### Scenario: The close proceeds once they are resolved

- **WHEN** the cashier resolves the listed deliveries and closes again
- **THEN** the close succeeds

### Requirement: Pending refunds are visible and actionable

The front SHALL show pending refunds for the branch with their order, customer, amount and
method, and SHALL allow an authorized user to confirm or cancel each one, a cancellation
requiring a reason. Pending refunds SHALL be shown at close time as information, without blocking
the close.

#### Scenario: Confirming a refund removes it from the list

- **WHEN** an authorized user confirms a pending refund
- **THEN** it disappears from the pending list

#### Scenario: Cancelling requires a reason

- **WHEN** a user cancels a refund without giving a reason
- **THEN** the action is refused and the reason is requested

#### Scenario: Refunds are shown at close without blocking

- **WHEN** a cashier closes a session with pending refunds and no unresolved deliveries
- **THEN** the refunds are shown as outstanding and the close still succeeds

### Requirement: Refund and verification controls follow permissions

Verifying a payment, confirming a refund and cancelling a refund SHALL be hidden or disabled for
users lacking the corresponding permission, and refused on direct attempt.

#### Scenario: Without permission the control is not offered

- **WHEN** a user without the required permission views an order awaiting verification or a
  pending refund
- **THEN** the corresponding action is unavailable
