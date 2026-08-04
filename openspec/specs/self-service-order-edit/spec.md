# self-service-order-edit Specification

## Purpose

Que el cliente corrija **su propio pedido** desde un enlace, sin esperar a que alguien lea un
WhatsApp: se me olvidó decir *sin lechuga*, quiero queso extra, quiero otra hamburguesa para mi
hermano.

Nació de **descartar** el camino obvio. La petición era "que el asistente pueda modificar un
pedido", y eso traía cuatro riesgos nuevos que el problema no necesitaba: el modelo tendría que
decidir un precio (`add_item` recibe el precio de quien llama), reescribir una nota de texto libre
sin comerse lo que ya decía, sostener una confirmación entre turnos, y ganarle una carrera a la
cocina. Mover la edición a una vista los disuelve los cuatro: el catálogo está delante, los precios
salen del read-model, las exclusiones se ven marcadas, y quien confirma es una persona mirando.

Dos invariantes lo sostienen. **El total nunca baja** — se comprueba una vez, sobre el pedido
resultante y no paso a paso, porque cambiar un producto es "quitar y poner" y por pasos el
intermedio siempre bajaría; de ella se deriva sola que cambiar una gaseosa por otra del mismo
precio valga y cambiarla por agua no. Y **quitar, bajar cantidad y cancelar no son autoservicio**:
eso lo resuelve una persona, y mandar a esta vista a quien quiere quitar algo es peor que no
mandarlo.

Las dos ventanas de edición son físicas, no administrativas: por ítem, mientras ninguna de sus
estaciones haya empezado; por pedido, hasta que la comida deja de estar al alcance — un domicilio
al salir, y un pedido de mesa o para recoger al quedar listo. Entre un pedido listo y una moto que
ya arrancó, la bolsa sigue en el pase y un cocinero todavía puede hacer una cosa más.

Fuera de alcance: que el asistente edite (sigue siendo de sólo lectura y este alcance lo reafirma),
cancelar y devolver, y editar un pedido de mostrador que nadie pidió por la carta.

## Requirements

### Requirement: An order edit link is a per-order capability

The system SHALL mint an edit token bound to a **single order**, and SHALL resolve an edit
session only through that token. The token SHALL NOT be the conversation's store token, which
identifies a contact rather than an order.

Resolving a token SHALL yield only that order. An expired, unknown or foreign-tenant token
SHALL be indistinguishable from one another to the caller.

#### Scenario: The link opens exactly one order

- **WHEN** a customer opens their edit link
- **THEN** they see that order and no other order of theirs

#### Scenario: A forwarded link cannot reach the rest of the customer's orders

- **WHEN** an edit token is used to request a different order
- **THEN** the request is refused and reveals nothing about that other order

#### Scenario: An expired token says nothing

- **WHEN** a token past its lifetime is presented
- **THEN** the response does not disclose whether the order exists

### Requirement: The total of an order never decreases

The system SHALL reject any edit whose resulting order total is lower than the total before the
edit. The comparison SHALL be made against the **resulting** order, not against each individual
operation.

This invariant — not an enumeration of allowed verbs — is what makes a same-price swap valid and
a cheaper swap invalid.

#### Scenario: A swap between equally priced products is accepted

- **WHEN** a customer swaps a product for another of the same price
- **THEN** the edit is accepted because the resulting total is unchanged

#### Scenario: A swap for something cheaper is refused

- **WHEN** a customer swaps a product for a cheaper one
- **THEN** the edit is refused and the order is left exactly as it was

#### Scenario: Intermediate steps do not decide

- **WHEN** an edit removes a line and adds a more expensive one in the same operation
- **THEN** the edit is accepted, because only the resulting total is compared

### Requirement: Removing, reducing and cancelling are not self-service

The system SHALL refuse, through this capability, any edit that removes a line, reduces a
quantity or cancels the order. Those SHALL remain staff operations.

#### Scenario: Removing a line is refused

- **WHEN** a customer attempts to remove an item from their order
- **THEN** the edit is refused and the customer is pointed at a person

#### Scenario: Cancelling is refused

- **WHEN** a customer attempts to cancel their order from the edit view
- **THEN** the order is unchanged and the customer is pointed at a person

### Requirement: An item is editable only while its kitchen work has not started

The system SHALL allow editing an item only while every one of that item's station tasks is
still `pending`. An item with any station task in progress, ready or beyond SHALL be read-only
through this capability.

The state SHALL be re-read at write time. A state read when the view was rendered SHALL NOT be
used to authorise the write.

#### Scenario: A note reaches an item nobody started

- **WHEN** a customer edits the note of an item whose stations are all pending
- **THEN** the note is saved and the kitchen sees it

#### Scenario: An item already being cooked is not edited

- **WHEN** a customer edits an item whose station started while the view was open
- **THEN** the edit is refused and the customer is told it is already being prepared

#### Scenario: One started item does not freeze the others

- **WHEN** one item of an order is in progress and another has not started
- **THEN** the one that has not started remains editable

### Requirement: The edit window closes when the food is out of reach

The system SHALL refuse every edit — additions included — once the food can no longer be
touched, which depends on how the order leaves:

- an order with a delivery, when that delivery reaches `in_transit` or beyond;
- any other order, when its kitchen state is `ready`.

The line is physical, not procedural: between a ready order and a delivery that has left, the
bag is still at the pass and a cook can still make one more thing. Once the driver is riding,
nothing can be done about it.

#### Scenario: Nothing changes on an order already on its way

- **WHEN** an order's delivery is `in_transit` and a customer tries to change anything
- **THEN** the edit is refused and the customer is offered a person

#### Scenario: A ready delivery waiting at the pass is still editable

- **WHEN** an order is ready but its delivery has not left yet
- **THEN** an addition is accepted and routed to the kitchen

#### Scenario: A pickup order closes when it is ready

- **WHEN** an order without a delivery reaches `ready`
- **THEN** every edit is refused, because the food is waiting on the counter

#### Scenario: The link explains itself once closed

- **WHEN** a customer opens the link for an order past its window
- **THEN** the view explains the order can no longer be changed and offers a person

### Requirement: Paid lines grow but never change identity

When an order has a registered payment, the system SHALL allow existing lines only to grow —
addons and quantity — and SHALL refuse changing the product of an existing line. Additions SHALL
create new lines rather than modify paid ones.

#### Scenario: Extra cheese on a paid burger

- **WHEN** a customer adds an addon to an item of an order that is already paid
- **THEN** the addon is attached and the amount owed increases

#### Scenario: A paid line does not change product

- **WHEN** a customer swaps the product of a line on a paid order
- **THEN** the edit is refused, so that what was paid for remains on record

#### Scenario: An addition to a paid order is a new line

- **WHEN** a customer adds a second burger to a paid order
- **THEN** a new line is created and the previously paid lines are untouched

### Requirement: What is added is sent to the kitchen

When the rest of the order has already been routed to the kitchen, the system SHALL route an
added item as part of the same edit. An item SHALL NOT be left billed and unrouted.

#### Scenario: Fries added mid-service reach a station

- **WHEN** a customer adds an item to an order already in the kitchen
- **THEN** the added item is routed and appears on the kitchen board

#### Scenario: An order not yet sent keeps staff control

- **WHEN** a customer adds an item to an order staff have not sent to the kitchen yet
- **THEN** the item joins the order as pending and staff send the order as usual

### Requirement: The amount owed is stated before it is charged

The system SHALL report, with any accepted edit, the resulting total and how much is still owed,
so it can be shown to the customer before they are charged at the door or the counter.

#### Scenario: The delta is known after an addition

- **WHEN** an edit increases the total of an order that had been settled
- **THEN** the response states the new total and the outstanding amount

### Requirement: Edits are attributed to the customer

The system SHALL record an edit made through this capability as performed by the customer via
the order's channel, not as an anonymous system action.

#### Scenario: An edit is traceable

- **WHEN** a customer edits their order through the link
- **THEN** the audit record shows the change was requested by the customer, not by staff
