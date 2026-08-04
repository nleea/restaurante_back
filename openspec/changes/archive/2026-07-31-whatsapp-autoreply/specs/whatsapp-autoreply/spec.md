## ADDED Requirements

### Requirement: Conversation states for automation

The conversation lifecycle SHALL support the states `greeted` and `bot` in addition to `new`,
`human` and `closed`. A conversation SHALL move from `new` to `greeted` when the automatic
greeting is emitted, and MAY move to `bot` only when an assistant is enabled and the customer
opts into it. Claiming by an employee SHALL move a conversation to `human` from any open
state.

#### Scenario: Greeting advances the state

- **WHEN** the automatic greeting is emitted on a `new` conversation
- **THEN** the conversation status becomes `greeted`

#### Scenario: An employee can take over at any point

- **WHEN** an employee claims a conversation in state `new`, `greeted` or `bot`
- **THEN** its status becomes `human` and no further automatic greeting is emitted for it

#### Scenario: `bot` is unreachable without an assistant

- **WHEN** no assistant is enabled for the tenant
- **THEN** no conversation reaches the `bot` state

### Requirement: Automatic greeting on a new conversation

The system SHALL emit the tenant's configured greeting as a reply to the first inbound message
of a conversation, exactly once per conversation. The greeting SHALL be sent through the
outbound gateway, and therefore SHALL only ever be a reply — the system SHALL NOT initiate a
conversation under any circumstance.

#### Scenario: First message is answered immediately

- **WHEN** a contact sends the first message of a new conversation
- **THEN** the configured greeting is sent back as an outbound message stored in the thread

#### Scenario: The greeting is not repeated

- **WHEN** the same contact sends several further messages in the same conversation
- **THEN** no further greeting is emitted

#### Scenario: The greeting fires regardless of content

- **WHEN** the first inbound message is a greeting, a question, a single character, or an
  unsupported media type
- **THEN** the greeting is emitted the same way, with no keyword matching

#### Scenario: A new conversation after the idle window greets again

- **WHEN** a contact writes again after the previous conversation closed on the idle window
- **THEN** a new conversation is opened and greeted once

#### Scenario: Greeting is disabled

- **WHEN** a tenant has the automatic greeting disabled
- **THEN** no greeting is emitted and the conversation stays `new` until a human claims it

### Requirement: Greeting reflects the branch's hours and menu link

The greeting SHALL be rendered per branch, substituting that branch's name, its
branch-addressed store link, and — when the branch is closed — its real next opening time
derived from the branch's operating hours. An open branch SHALL receive the open variant of
the text; a closed branch SHALL receive the closed variant.

#### Scenario: Open branch gets the menu link

- **WHEN** the greeting is emitted for a branch that is currently open
- **THEN** the message carries that branch's store link

#### Scenario: Closed branch states when it opens

- **WHEN** the greeting is emitted for a branch that is currently closed
- **THEN** the message uses the closed variant and states that branch's real next opening time

#### Scenario: Each branch sends its own link

- **WHEN** two branches of the same tenant each receive a first message
- **THEN** each greeting carries its own branch's link, from a single tenant-level text

### Requirement: Assistant offer only when entitled

The greeting SHALL offer the conversational assistant only when the tenant has it enabled.
When it is not enabled, the greeting SHALL omit the offer, and a customer asking to talk to
someone SHALL be routed to the human inbox rather than to an assistant.

#### Scenario: No assistant, no offer

- **WHEN** a tenant without the assistant enabled emits a greeting
- **THEN** the message does not offer to talk to an assistant

#### Scenario: Assistant enabled, offer present

- **WHEN** a tenant with the assistant enabled emits a greeting
- **THEN** the message offers it alongside the store link

### Requirement: Tokenised store link

When a store link is sent to a contact, the system SHALL mint an opaque, random token on the
conversation with a configured lifetime (default 24 hours) and include it in the link. The
token SHALL be reusable while it is valid and SHALL resolve only to the contact, never to an
order or to any other customer data.

#### Scenario: The link carries a token

- **WHEN** a greeting or an agent's "send the menu" action sends the store link
- **THEN** the link includes a token bound to that conversation

#### Scenario: The token can be used more than once

- **WHEN** the customer opens the link twice within its lifetime
- **THEN** it resolves both times

#### Scenario: An expired token stops resolving

- **WHEN** the token's lifetime has passed
- **THEN** it no longer resolves, and the customer can still order without it

#### Scenario: A token reveals only the contact

- **WHEN** a token is resolved
- **THEN** only the contact's name and phone are returned, with no order or history data

### Requirement: Order status messages from a per-tenant mapping

The system SHALL send a customer-facing message on an order or delivery transition only when
the tenant's mapping declares that transition as customer-facing. Transitions not in the
mapping SHALL send nothing. The default mapping SHALL cover order received (with the order
summary), out for delivery, delivered, and cancelled.

#### Scenario: A mapped transition messages the customer

- **WHEN** a delivery moves to `on_route` and the tenant maps it
- **THEN** the customer receives the corresponding message

#### Scenario: Internal churn is silent

- **WHEN** an order item moves from `pending` to `in_progress`, or a delivery to `preparing`
  or `assigned`, and the tenant has not mapped them
- **THEN** no customer message is sent

#### Scenario: Pickup-only tenant opts into ready

- **WHEN** a tenant maps the kitchen `ready` transition
- **THEN** the customer receives a "ready to collect" message when the order is ready

#### Scenario: The confirmation carries the order summary

- **WHEN** the order-received message is sent
- **THEN** it includes the order number and its total

### Requirement: Every automatic message is emitted at most once

The system SHALL record an emission key for each automatic message — the conversation for the
greeting, and the pair of order and customer-facing state for status messages — and SHALL NOT
send a message whose key has already been recorded. The record SHALL be written atomically so
that concurrent attempts result in exactly one send.

#### Scenario: A bouncing status does not message twice

- **WHEN** an order returns to a state whose message was already sent
- **THEN** no second message is sent

#### Scenario: Concurrent attempts send once

- **WHEN** two workers process the same transition at the same time
- **THEN** exactly one message is sent

#### Scenario: A retried event is not a second message

- **WHEN** the same transition notification is delivered more than once
- **THEN** the customer receives one message

### Requirement: Automatic messages respect the outbound invariant

Every automatic message SHALL be sent through the outbound gateway and SHALL therefore be
suppressed when the customer has no contact record with an inbound message. Suppression SHALL
NOT fail the order or the transition that triggered it.

#### Scenario: A customer who never wrote is not messaged

- **WHEN** an order is placed by a customer with no WhatsApp contact
- **THEN** no message is attempted and the order proceeds normally

#### Scenario: Suppression is not an error

- **WHEN** an automatic message is suppressed
- **THEN** the triggering order or delivery transition completes unaffected

### Requirement: Tenant-level autoreply settings

The system SHALL store, per tenant, the greeting text in its open and closed variants, whether
the greeting is enabled, whether the assistant is offered, the conversation idle window, the
store token lifetime, and the mapping of transitions to customer messages. With the greeting
disabled and the mapping empty, the channel SHALL behave exactly as it did without this
capability.

#### Scenario: Settings drive the behaviour

- **WHEN** a tenant edits the greeting text and the transition mapping
- **THEN** subsequent greetings and status messages use the new values

#### Scenario: Fully disabled is inert

- **WHEN** the greeting is disabled and the mapping is empty
- **THEN** no automatic message is ever emitted, and conversations are answered only by humans
