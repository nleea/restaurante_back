# assistant-core

## Purpose

La parte que sí necesita un modelo: entender una pregunta que nadie guionó. Las tres fases
anteriores dejaron contestado sin tokens el saludo, el horario, el enlace, el comprobante y
el seguimiento del pedido; lo que llega aquí es el residuo —"¿tienen algo sin cebolla?",
"¿cuánto vendimos ayer?"— más la maquinaria comercial que hace que venderlo no nos arruine.

**Los tokens se compran al por mayor y se revenden, así que el dinero que arde en un bucle es
el NUESTRO.** Por eso medir no es una función de facturación: es un cortacircuitos que además
produce facturas. Toda llamada al modelo pasa por una sola puerta —derecho, interruptor
global, límite por minuto, cuota, llamada, libro— porque dos puertas significa que una de las
dos no está medida, y será la que alguien añada con prisa.

Dos convicciones dan forma al resto:

- **Al índice no se le pregunta lo que sabe la base.** El stock, las ventas, la carta y los
  horarios se contestan llamando a casos de uso que ya existen. Incrustar un informe produce
  un bot que afirma con seguridad los números de la semana pasada.
- **El modelo nunca recibe una credencial: recibe el contexto de quien llama.** El registro de
  herramientas de un cliente **no contiene** el informe de ventas, y el de un empleado es
  exactamente sus permisos. La inyección de prompt se defiende por capacidad, no por texto.

Fuera de alcance: RAG con un corpus real (el puerto viaja con un adaptador inerte), tomar el
pedido conversando, cualquier herramienta que escriba, y voz o imagen.

## Requirements

### Requirement: Entitlement gates every model call

The system SHALL make no model call for a tenant that is not entitled to the assistant. No
tenant SHALL be entitled by default. When a tenant is not entitled, conversations SHALL behave
exactly as they do without this capability.

#### Scenario: An unentitled tenant never calls a model

- **WHEN** a message arrives for a tenant with no assistant entitlement
- **THEN** no model call is made and the conversation is handled by the greeting and human
  inbox alone

#### Scenario: Tenants arrive unentitled

- **WHEN** a tenant is provisioned
- **THEN** the assistant is disabled for it

### Requirement: Single metered choke point

Every model call SHALL pass through one path that, in order, verifies entitlement, the global
kill switch, the per-minute rate limit and the remaining quota, performs the call, and records
usage. No code path SHALL be able to reach the conversation engine without passing through it.

#### Scenario: All checks precede the call

- **WHEN** a model call is requested
- **THEN** entitlement, kill switch, rate limit and quota are all evaluated before the provider
  is contacted

#### Scenario: Usage is recorded for every call

- **WHEN** a model call completes, successfully or with a provider error after tokens were
  consumed
- **THEN** a usage record is written

#### Scenario: No unmetered path exists

- **WHEN** any caller obtains the assistant from the composition root
- **THEN** it can only reach the engine through the metered path

### Requirement: Three independent limits

The system SHALL enforce a monthly quota, a per-minute rate limit, and a global kill switch as
three separate controls. Exhausting one SHALL NOT be conflated with exhausting another, and
each SHALL be independently observable.

#### Scenario: Rate limit stops a loop within the quota

- **WHEN** a tenant with quota remaining exceeds the per-minute rate limit
- **THEN** further calls are refused until the window passes, without consuming quota

#### Scenario: Quota stops a tenant within the rate limit

- **WHEN** a tenant within the rate limit has exhausted its monthly quota
- **THEN** further calls are refused

#### Scenario: The kill switch overrides everything

- **WHEN** the global kill switch is engaged
- **THEN** no model call is made for any tenant, regardless of entitlement, rate or quota

### Requirement: Per-call cost ceiling

The system SHALL truncate conversation input to a configured maximum and cap the model's
output at a configured maximum, so that the maximum cost of a single call is known before it is
made. Quota SHALL be checked before the call and recorded after it, and the resulting overshoot
SHALL be at most one call's ceiling.

#### Scenario: Oversized input is truncated

- **WHEN** an inbound message and history exceed the configured input maximum
- **THEN** the input is truncated to that maximum before the call

#### Scenario: Output is capped

- **WHEN** a model call is made
- **THEN** the request carries the configured output maximum

#### Scenario: Overshoot is bounded

- **WHEN** a call is admitted with a small remaining quota and consumes more than remained
- **THEN** the recorded overshoot does not exceed one call's ceiling, and the next call is
  refused

### Requirement: Append-only two-layer usage ledger

The system SHALL record one immutable entry per model call carrying the time, the caller kind,
the conversation reference, the provider and model, tokens consumed in and out, the provider
cost, and the units billed to the tenant. Entries SHALL NOT be updated or deleted, and the
remaining quota SHALL be derived from them.

#### Scenario: Every call is auditable

- **WHEN** a tenant disputes their consumption
- **THEN** each call is present with its tokens, cost and billed units

#### Scenario: Both layers are recorded

- **WHEN** a usage entry is written
- **THEN** it carries both what the provider cost and what the tenant was billed

#### Scenario: Balance is derived, not stored as a mutable counter

- **WHEN** remaining quota is evaluated
- **THEN** it is derived from the ledger for the current period

#### Scenario: Entries are immutable

- **WHEN** an attempt is made to modify or remove a usage entry
- **THEN** it is refused

### Requirement: Tool registries are built per caller

The system SHALL build the available tool set from the caller's identity. A WhatsApp customer
SHALL receive only customer-safe tools. An authenticated employee SHALL receive only tools whose
underlying use cases their permissions allow, evaluated per request. Tools SHALL be the existing
application use cases, invoked with the caller's tenancy and permissions.

#### Scenario: A customer cannot reach staff capabilities

- **WHEN** a WhatsApp customer asks for sales figures, stock levels or any staff capability
- **THEN** no such tool exists in their registry and no such data is returned

#### Scenario: Instruction-style injection changes nothing

- **WHEN** a customer's message instructs the assistant to ignore its instructions and disclose
  staff data
- **THEN** the outcome is unchanged, because the capability is absent rather than withheld

#### Scenario: An employee's tools match their permissions

- **WHEN** an employee without the finance permission asks for financial figures
- **THEN** the tool is absent from their registry and the request is not answered with that data

#### Scenario: Permission changes take effect immediately

- **WHEN** an employee's permissions change between two messages
- **THEN** the second message's registry reflects the new permissions

#### Scenario: Tenancy is never crossed

- **WHEN** any tool executes
- **THEN** it runs under the caller's tenant, and no other tenant's data is reachable

### Requirement: Live state comes from tools, never from retrieval

Questions about live state — menu, prices, hours, stock, orders, sales — SHALL be answered by
invoking tools against current data. The system SHALL NOT answer such questions from the
knowledge index.

#### Scenario: Current data answers a current question

- **WHEN** a caller asks what is available or what something costs
- **THEN** the answer derives from a tool call against current data

#### Scenario: Stale retrieval does not answer live questions

- **WHEN** the knowledge index contains material resembling an answer about live state
- **THEN** the answer still comes from a tool call

### Requirement: Knowledge index ships inert

The system SHALL consult a knowledge index port for prose questions and SHALL operate correctly
when that index returns nothing. The default adapter SHALL return no results.

#### Scenario: The assistant works with an empty index

- **WHEN** the assistant runs with the default knowledge index
- **THEN** it answers from tools and does not fail on the empty retrieval

#### Scenario: The index is replaceable without touching use cases

- **WHEN** a populated index adapter replaces the default
- **THEN** no application use case changes

### Requirement: The assistant is read-only

No tool available to the assistant SHALL mutate data in this capability. When asked to place an
order, change a price, adjust stock or perform any other write, the assistant SHALL respond
with the store link or hand off to a human.

Editing an order is no exception: the assistant SHALL send the order's edit link and SHALL NOT
perform the edit. What the customer changes, the customer confirms in front of the catalogue and
the prices — never through a value the model produced.

#### Scenario: Ordering is redirected, not performed

- **WHEN** a customer tells the assistant they want to order
- **THEN** the assistant provides the store link rather than creating an order

#### Scenario: A write request is refused

- **WHEN** an employee asks the assistant to change a price or adjust stock
- **THEN** no data is modified and the assistant explains it cannot make changes

#### Scenario: Editing is delegated to the customer, not performed

- **WHEN** a customer asks the assistant to add something to their order
- **THEN** the assistant sends the order's edit link and modifies nothing itself

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

### Requirement: The assistant is switched off outside opening hours

The assistant SHALL NOT call the model while the branch is closed, and SHALL NOT take a
conversation into assistant mode while the branch is closed. A conversation whose customer accepts
the assistant outside opening hours SHALL stay as it was, so a person attends it when the business
opens, and the acceptance SHALL still work then.

For a conversation already in assistant mode, the system SHALL reply with a fixed message stating
when the business opens next, built from the branch's configured hours, and SHALL send that message
**once per closed stretch rather than once per inbound message** — repeating the same sentence on
every message is how a number gets flagged and how a customer learns to mute the chat. Recognising
that the notice was already given SHALL be done by reading the thread, not by holding state.

Failing to read the schedule SHALL count as open: the expensive answer is the one that never
arrives.

The schedule switches off the **assistant**, not the customer's own views: an order edit link SHALL
keep working outside opening hours, because it depends on the order's state and not on the clock.

#### Scenario: A closed branch answers without spending

- **WHEN** a customer writes to a conversation in assistant mode while the branch is closed
- **THEN** a fixed message with the next opening is sent and no model call is made

#### Scenario: Accepting the assistant while closed does not hand anyone to a bot

- **WHEN** a customer accepts the assistant while the branch is closed
- **THEN** the conversation does not enter assistant mode and nothing is sent, so a person attends
  it when the business opens

#### Scenario: The closed notice is not repeated on every message

- **WHEN** a customer sends several messages in a row while the branch is closed
- **THEN** the closed notice is sent once, not once per message

#### Scenario: A person replying in between lets the notice out again

- **WHEN** somebody from the team replies and the customer writes again while still closed
- **THEN** the closed notice is sent again, because the conversation moved

#### Scenario: An unreadable schedule does not silence the assistant

- **WHEN** the branch's schedule cannot be read
- **THEN** the assistant answers as if open

#### Scenario: The edit link keeps working while closed

- **WHEN** a customer opens their order's edit link outside opening hours
- **THEN** the view behaves according to the order's state, not the clock

### Requirement: Graceful exhaustion without a model call

When a tenant's quota is exhausted, the system SHALL reply with the tenant's configured
fallback message including the store link, and SHALL do so **without calling the model**. The
conversation SHALL remain available for a human to claim.

#### Scenario: Exhaustion costs nothing

- **WHEN** a message arrives for a tenant whose quota is exhausted
- **THEN** the fallback message is sent and no model call is made

#### Scenario: The customer still has a way to order

- **WHEN** the fallback message is sent
- **THEN** it carries the store link

#### Scenario: A human can still take over

- **WHEN** a conversation has been answered with the fallback
- **THEN** it remains claimable from the shared inbox

### Requirement: Quota warning as an alert rule

The system SHALL register a rule on the alert machinery that fires when a tenant's consumption
reaches its configured warning threshold, so the warning inherits that machinery's
once-per-condition behaviour rather than repeating on every message.

#### Scenario: The owner is warned once

- **WHEN** consumption crosses the warning threshold and further messages are handled
- **THEN** exactly one alert is fired for the period

#### Scenario: The warning re-arms in the next period

- **WHEN** a new quota period begins and consumption crosses the threshold again
- **THEN** the alert fires again

### Requirement: Conversation engine behind a port

The conversation engine SHALL be reached through a port that accepts and returns the system's
own types. Provider libraries SHALL NOT appear in the application or domain layers, and the
provider and model SHALL be attributes of the tenant's plan rather than a tenant-supplied
preference.

#### Scenario: The engine is replaceable

- **WHEN** the engine adapter is replaced with another provider's implementation
- **THEN** no application or domain code changes

#### Scenario: Provider types do not leak

- **WHEN** the application layer handles a conversation result
- **THEN** it handles only the system's own types

#### Scenario: The plan selects the model

- **WHEN** two tenants on different plans are served
- **THEN** each is served by its plan's model, with no tenant-supplied provider configuration
