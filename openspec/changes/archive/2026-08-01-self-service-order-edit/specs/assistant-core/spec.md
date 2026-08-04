## ADDED Requirements

### Requirement: Change requests are routed to the right door

The assistant SHALL classify a request to change an existing order and route it: additions,
addons, notes and product swaps SHALL be answered with that order's edit link; removals, quantity
reductions, cancellations and refunds SHALL be handed off to a person.

Sending a customer who wants to remove something to a view that cannot remove it SHALL be treated
as a wrong answer, not as a partial one.

#### Scenario: An addition gets the link

- **WHEN** a customer says they forgot to ask for extra cheese
- **THEN** the assistant sends the edit link for their order

#### Scenario: A removal gets a person

- **WHEN** a customer says they no longer want one of the items
- **THEN** the assistant does not send the edit link and hands the conversation to a person

#### Scenario: The link belongs to the order, not to the menu

- **WHEN** the assistant answers a change request
- **THEN** it sends the link that opens that customer's order, not the general menu link

### Requirement: The assistant does not answer outside opening hours

When the branch is closed, the assistant SHALL NOT call the model. It SHALL reply with a fixed
message stating when the business opens next, built from the branch's configured hours.

Silence is not the intent: the reply costs no tokens and still tells the customer something
useful.

#### Scenario: A closed branch answers without spending

- **WHEN** a customer writes to a conversation in assistant mode while the branch is closed
- **THEN** a fixed message with the next opening is sent and no model call is made

#### Scenario: The edit link keeps working while closed

- **WHEN** a customer opens their order's edit link outside opening hours
- **THEN** the view behaves according to the order's state, not the clock

## MODIFIED Requirements

### Requirement: The assistant is read-only

No tool available to the assistant SHALL mutate data in this capability. When asked to place an
order, change a price, adjust stock or perform any other write, the assistant SHALL respond with
a link the customer drives themselves, or hand off to a human.

Editing an order is no exception: the assistant SHALL send the order's edit link and SHALL NOT
perform the edit. What the customer changes, the customer confirms in front of the catalogue and
the prices — never through a value the model produced.

#### Scenario: Ordering is redirected, not performed

- **WHEN** a customer tells the assistant they want to order
- **THEN** the assistant provides the store link rather than creating an order

#### Scenario: A write request is refused

- **WHEN** an employee asks the assistant to change a price or adjust stock
- **THEN** no data is modified and the assistant explains it cannot make changes

#### Scenario: Editing an order is redirected too

- **WHEN** a customer asks the assistant to change something in their order
- **THEN** the assistant sends the edit link and modifies nothing itself
