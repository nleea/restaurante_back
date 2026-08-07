# customer-payment-proof Specification

## Purpose

Lo que el cliente **dice** haber pagado, con su comprobante — y que deliberadamente **no es un
pago**. Un cliente que transfiere desde su banco o desde Nequi manda una captura, y alguien del
restaurante tiene que mirarla y decidir si la plata llegó de verdad. Esta capability es el sitio
donde esa declaración vive mientras nadie la ha mirado.

La decisión que la sostiene entera es que las declaraciones viven en su **propia tabla**, no como
una fila más en los pagos del pedido: `payments_total` suma los pagos, y de ahí cuelgan la
verificación de cocina, el cierre del pedido, la caja y el arqueo. Una declaración ahí —aunque
llevara `verified = false`— haría que un pedido entrara a cocina porque el cliente escribió que
pagó, y obligaría a excluir ese estado en cada consulta de dinero del sistema; la primera que se
olvidara sería un descuadre.

**Lo que no está en los pagos del pedido no es dinero en ninguna pantalla.** Esa es toda la idea.

De ahí se derivan las demás reglas: un claim es una ayuda para decidir y nunca la decisión;
verificar sigue siendo posible sin ningún claim; y quien acepta o rechaza es siempre una persona,
que queda registrada. El cliente se entera del resultado en los dos sentidos, y un rechazo lleva el
motivo porque el cliente lo va a leer.

Fuera de alcance: pasarelas de pago (verificar es un humano mirando un comprobante), cobrar deudas
de fiado con un comprobante (un claim cuelga de un pedido), y comparar automáticamente el importe
de la captura con el total.

## Requirements

### Requirement: A customer payment claim is not a payment

The system SHALL let a customer declare that they paid an order and attach a receipt. The
declaration SHALL be recorded separately from the order's payments and SHALL NOT change the
order's paid amount, its outstanding balance, its status, or its ability to reach the kitchen.

Only a staff verification SHALL register money for an order.

#### Scenario: A declaration leaves the money untouched

- **WHEN** a customer declares a payment for an order
- **THEN** the order's paid total, outstanding amount and status are exactly what they were

#### Scenario: A declaration does not open the kitchen

- **WHEN** a prepaid order with a pending declaration is routed to the kitchen
- **THEN** routing is refused for the same reason as before the declaration existed

#### Scenario: Only verification registers money

- **WHEN** staff verify the payment of an order that has a pending declaration
- **THEN** a payment for the order's outstanding amount is registered
- **AND** it is the verification, not the declaration, that produced it

### Requirement: A claim carries what a person needs to decide

A claim SHALL record the amount the customer says they paid, the method they used, the receipt
image, and when it was made. It SHALL belong to exactly one order.

#### Scenario: The claim shows the customer's own figures

- **WHEN** staff open an order with a pending claim
- **THEN** they see the declared amount, the method, the receipt and the time it arrived

#### Scenario: A claim belongs to one order only

- **WHEN** a claim is read
- **THEN** it is reachable only through the order it was made for

### Requirement: Claims are resolved by a person, in both directions

Staff SHALL be able to accept a claim — which happens as part of verifying the payment, from the
order screen where the kitchen is fired — or to reject it with a reason. Accepting SHALL mean a
person checked that the money actually arrived; the system SHALL NOT confirm a payment on its own. A resolved claim SHALL record who resolved it and when.

Rejecting SHALL NOT register any money and SHALL leave the customer able to send another claim.

#### Scenario: Verifying accepts the pending claims

- **WHEN** staff verify the payment of an order that has pending claims
- **THEN** those claims are marked accepted and attributed to the verifying employee

#### Scenario: Rejecting costs nothing and reopens the door

- **WHEN** staff reject a claim with a reason
- **THEN** no payment is registered
- **AND** the customer may submit a new claim for that order

#### Scenario: Verification does not require a claim

- **WHEN** staff verify a payment for an order with no claim at all
- **THEN** verification succeeds exactly as it did before this capability existed

### Requirement: The customer learns the outcome

The system SHALL notify the customer when a claim is accepted or rejected, whenever the order has
a reachable customer channel. A rejection SHALL carry the reason.

#### Scenario: An accepted claim is confirmed

- **WHEN** a claim is accepted
- **THEN** the customer is told their payment was confirmed

#### Scenario: A rejected claim says why

- **WHEN** a claim is rejected with a reason
- **THEN** the customer is told, with that reason, and can send another receipt

#### Scenario: No channel, no failure

- **WHEN** the order has no reachable customer channel
- **THEN** the claim is still resolved and nothing is sent

### Requirement: Pending claims are bounded per order

The system SHALL limit how many unresolved claims an order may hold and SHALL refuse further
declarations beyond that limit until a person resolves the pending ones.

#### Scenario: The limit is reached

- **WHEN** a customer submits more claims than the limit allows on the same order
- **THEN** the extra submission is refused and the existing claims are untouched

### Requirement: A claim can be born from a chat message

An employee SHALL be able to turn an inbound chat message carrying an image or a PDF into a payment
claim for one of that contact's unsettled orders, choosing the order and confirming the amount. The
resulting claim SHALL be indistinguishable from one the customer uploaded through the order's link:
it SHALL carry the file, it SHALL be pending, and it SHALL be resolved by a person in both
directions like any other.

The system SHALL NOT create a claim on its own when a file arrives. A photograph is not a
declaration of payment: customers send pictures of streets, menus, documents and their own address,
and a claim created by arrival alone eventually becomes a "receipt" that is a photo of a dog — after
which staff learn to ignore the notice.

Creating a claim this way SHALL require the permission that registering a payment requires, not the
permission to attend conversations: it is a step on the money path.

#### Scenario: An employee turns a receipt photo into a claim

- **WHEN** an employee viewing an inbound image chooses to use it as the receipt for an unsettled
  order of that contact
- **THEN** a pending claim is created for that order, carrying that file, and the order shows it
  like any other claim

#### Scenario: The amount starts from the balance and can be corrected

- **WHEN** the employee opens the action
- **THEN** the amount is prefilled with the order's outstanding balance and can be edited before
  confirming

#### Scenario: Arrival alone creates nothing

- **WHEN** a contact with an unsettled order sends any image
- **THEN** no claim is created until a person says it is a receipt

#### Scenario: Attending is not enough

- **WHEN** a user who may attend conversations but may not register payments tries to create a claim
  from a message
- **THEN** the action is refused

#### Scenario: Only the contact's own unsettled orders are offered

- **WHEN** the employee opens the action
- **THEN** the orders offered are the ones belonging to that contact and still unsettled, and no
  other customer's order can be chosen
