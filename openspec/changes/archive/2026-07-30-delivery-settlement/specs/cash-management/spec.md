## ADDED Requirements

### Requirement: A session cannot close while deliveries are unresolved

Closing a cash session SHALL be refused while any of its deliveries is unresolved. A delivery is
**resolved** when it is `delivered` or `not_delivered`; it is **unresolved** while it is `pending`,
`assigned` or `in_transit`. The refusal SHALL identify the unresolved deliveries so they can be
acted on.

There is no override. The way out is to resolve the delivery by saying what happened to it, which
is always possible — any delivery can be marked not delivered from any non-terminal state. That
records the outcome on the order, where it belongs, instead of in a note attached to the close.

#### Scenario: Close is refused with a delivery still out

- **WHEN** an authorized user closes a session that has an `in_transit` delivery
- **THEN** the system responds with a conflict error identifying the unresolved deliveries
- **AND** the session remains open

#### Scenario: Close is refused with a delivery that never left

- **WHEN** an authorized user closes a session that has a `pending` or `assigned` delivery
- **THEN** the system responds with a conflict error

#### Scenario: Resolving the last delivery unblocks the close

- **WHEN** the last unresolved delivery of a session is marked delivered or not delivered
- **AND** the session is closed
- **THEN** the close succeeds

#### Scenario: Not delivered counts as resolved

- **WHEN** a session whose only delivery is `not_delivered` is closed
- **THEN** the close succeeds

#### Scenario: Uncollected orders alone do not block

- **WHEN** a session with uncollected dine-in orders and no unresolved deliveries is closed
- **THEN** the close succeeds

## MODIFIED Requirements

### Requirement: Pending summary before closing a session

The system SHALL provide, for an open cash session, a pending summary reporting the session's uncollected orders (count and total with an unpaid remainder) and **unresolved** deliveries (count of deliveries that are neither `delivered` nor `not_delivered`). The unresolved deliveries in this summary are the ones that block the close; the uncollected orders are advisory.

#### Scenario: Summary reflects unresolved work

- **WHEN** the pending summary is requested for an open session with unpaid orders and deliveries still out
- **THEN** it returns the count and total of uncollected orders and the count of unresolved deliveries for that session

#### Scenario: A not-delivered delivery is not counted as unresolved

- **WHEN** the pending summary is requested for a session whose delivery was marked `not_delivered`
- **THEN** that delivery is not counted among the unresolved

#### Scenario: Clean session

- **WHEN** the pending summary is requested for a session whose orders are all paid and deliveries all resolved
- **THEN** it reports zero uncollected and zero unresolved

## REMOVED Requirements

### Requirement: Force-close is never blocked by pending items

**Reason**: Un domicilio sin resolver puede significar efectivo en el bolsillo de alguien o comida
en la calle sin desenlace escrito. Dejar cerrar el turno con eso pendiente es justo cómo se pierde
ese dato, que es el que hace cuadrar la caja. La contrapartida —que un cierre pueda quedar
trabado— se elimina permitiendo marcar `not_delivered` desde cualquier estado no terminal, de modo
que siempre existe una salida honesta.

Los pedidos sin cobrar (`uncollected`) siguen siendo solo informativos: nunca bloquearon y siguen
sin bloquear.

**Migration**: El cierre pasa a responder conflicto mientras haya domicilios sin resolver. Quien
cierre debe resolver cada domicilio (entregado o no entregado, con su motivo) antes. Se recomienda
desplegar con la caja cerrada: un turno abierto en el momento del despliegue puede encontrarse
bloqueado por entregas antiguas que nadie resolvió, y hay que marcarlas una vez.
