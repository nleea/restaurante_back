## ADDED Requirements

### Requirement: Keyword FAQs answer free-text questions

The system SHALL evaluate an inbound message against the tenant's ordered list of enabled FAQs and
SHALL reply with the text of the first FAQ whose triggers match. Matching SHALL be case-insensitive,
accent-insensitive and insensitive to singular/plural, and a trigger SHALL match only as a **whole
word or whole phrase** — never as a substring. There SHALL be no regular expressions, no stemming
and no natural-language inference: a message that does not contain a configured trigger SHALL
receive nothing.

The order of the list SHALL be the matching priority, and it SHALL be editable by the tenant.

#### Scenario: A configured question is answered

- **WHEN** a customer asks where the branch is, using one of the location FAQ's triggers
- **THEN** the location FAQ's text is sent, rendered for that branch

#### Scenario: An inflection does not match

- **WHEN** a customer writes "ya pagué y no me llegó" and a FAQ has the trigger `pago`
- **THEN** no FAQ is sent, because `pago` is not a whole word of that message

#### Scenario: Plural and accents do not matter

- **WHEN** a FAQ has the trigger `domicilio` and the customer writes "¿hacen domicilios?"
- **THEN** that FAQ matches

#### Scenario: Priority is the list order

- **WHEN** a message matches triggers of two enabled FAQs
- **THEN** only the one earlier in the list is sent

#### Scenario: An unknown question is silent

- **WHEN** a message matches no trigger of any enabled FAQ
- **THEN** nothing is sent and the message waits for a human

### Requirement: FAQs never answer over an active order or a request for a person

Before matching, the system SHALL stay silent when any of the following holds: the contact has an
order that is not delivered, cancelled or closed within the conversation idle window; or the message
asks for a human, or asks to cancel, annul, return or refund. When the check for active orders
cannot be performed, the system SHALL stay silent.

Silence is the correct outcome here, not a degradation: a `greeted` conversation already produces no
automatic reply, so staying quiet keeps the status quo, while answering a leaflet to somebody in the
middle of an order is the worst possible result.

#### Scenario: A customer mid-order is not answered by a FAQ

- **WHEN** a contact with an order still in progress writes "mi dirección es la calle 5 #3-20"
- **THEN** no FAQ is sent, even though the location FAQ's trigger matches

#### Scenario: A stale order does not silence FAQs forever

- **WHEN** the contact's only unfinished order is older than the conversation idle window
- **THEN** FAQs are evaluated normally

#### Scenario: Asking for a person wins over any FAQ

- **WHEN** a message asks to talk to somebody, or to cancel or refund an order
- **THEN** no FAQ is sent and the message is left for a human

#### Scenario: A failed lookup stays silent

- **WHEN** the active-order check cannot be completed
- **THEN** no FAQ is sent

### Requirement: A FAQ reply leaves the conversation to a human

Sending a FAQ SHALL NOT change the conversation status and SHALL NOT remove the conversation from
the shared inbox. A conversation in `greeted` SHALL remain in `greeted` after being answered by a
FAQ, and SHALL remain claimable by an employee.

This is what makes a wrong match recoverable: the customer is never left talking to a bot, and a
person still sees the thread.

#### Scenario: The thread stays claimable

- **WHEN** a FAQ answers a conversation in `greeted`
- **THEN** the status is still `greeted` and the conversation is still listed in the inbox

#### Scenario: A wrong answer is not a lost customer

- **WHEN** a FAQ matches a message it should not have
- **THEN** the customer's message is still in the thread for an employee to answer

### Requirement: FAQs are answered regardless of opening hours

FAQs SHALL be evaluated and answered whether the branch is open or closed. A FAQ reply SHALL NOT
promise attention, and no text SHALL be appended to a FAQ automatically — what the customer receives
SHALL be exactly what the tenant wrote, with its placeholders resolved.

Unlike the conversational assistant, which the schedule switches off, a FAQ is a sign on the door:
the two questions that arrive at night are precisely the opening hours and the address.

#### Scenario: A closed branch still answers the address

- **WHEN** a customer asks where the branch is while it is closed
- **THEN** the location FAQ is sent

#### Scenario: Nothing is appended by the system

- **WHEN** a FAQ is sent while the branch is closed
- **THEN** the message contains only the tenant's text, with no system-added closing notice

### Requirement: Hours line placeholder

The system SHALL provide an `{hours_line}` placeholder, valid in FAQ texts, that resolves against the
branch's operating hours and the branch's local time: when the branch is open it SHALL state until
what time it is open today; when it is closed it SHALL state that it is closed and when it opens
next. When the branch has no hours configured, the placeholder SHALL resolve to nothing rather than
being left visible to the customer.

`{next_opening}` SHALL NOT be used for this purpose: it deliberately skips today's openings that
have already passed, so it reads wrongly for most of the working day.

#### Scenario: Open branch states today's closing time

- **WHEN** a FAQ using `{hours_line}` is sent while the branch is open
- **THEN** the message states until what time it is open today

#### Scenario: Closed branch states the next opening

- **WHEN** the same FAQ is sent while the branch is closed
- **THEN** the message states that it is closed and when it opens next

#### Scenario: A branch without hours does not show a broken message

- **WHEN** the branch has no operating hours configured
- **THEN** the placeholder resolves to nothing and the customer never sees `{hours_line}` literally

### Requirement: Reserved trigger vocabulary is refused when saving

The system SHALL refuse to save a FAQ whose trigger **contains** a word reserved by the channel —
the assistant opt-in words, the words that hand a conversation to a person, and the words that
signal a cancellation or a refund — and SHALL name the offending trigger and the reserved word in
the error.

Refusing on containment rather than on equality is deliberate: a trigger such as `cancelaciones`
would pass an equality check and then never fire, because the message that contains it also contains
a reserved word. A FAQ that is enabled and can never match is worse than a rejected one.

#### Scenario: A reserved word is refused

- **WHEN** a tenant saves a FAQ with the trigger `asistente`
- **THEN** saving is refused with a message naming the trigger and why it is reserved

#### Scenario: Containing a reserved word is also refused

- **WHEN** a tenant saves a FAQ with the trigger `cancelaciones`
- **THEN** saving is refused, explaining that those messages are answered by a person

#### Scenario: Ordinary triggers save normally

- **WHEN** a tenant saves a FAQ with triggers that contain no reserved word
- **THEN** the FAQ is stored and takes effect for subsequent messages

## MODIFIED Requirements

### Requirement: Conversation states for automation

The conversation lifecycle SHALL support the states `greeted` and `bot` in addition to `new`,
`human` and `closed`. A conversation SHALL move from `new` to `greeted` when the automatic
greeting is emitted, and MAY move to `bot` only when an assistant is enabled and the customer
opts into it. Claiming by an employee SHALL move a conversation to `human` from any open
state.

A conversation in `greeted` MAY additionally receive keyword FAQ replies, which SHALL NOT change its
status. FAQs SHALL NOT be evaluated in any other state: `new` belongs to the greeting, `bot` belongs
to the assistant, and `human` belongs to the employee who claimed it.

#### Scenario: Greeting advances the state

- **WHEN** the automatic greeting is emitted on a `new` conversation
- **THEN** the conversation status becomes `greeted`

#### Scenario: An employee can take over at any point

- **WHEN** an employee claims a conversation in state `new`, `greeted` or `bot`
- **THEN** its status becomes `human` and no further automatic greeting is emitted for it

#### Scenario: `bot` is unreachable without an assistant

- **WHEN** no assistant is enabled for the tenant
- **THEN** no conversation reaches the `bot` state

#### Scenario: The first message only gets the greeting

- **WHEN** the first inbound message of a conversation would also match a FAQ trigger
- **THEN** only the greeting is sent, because the message is evaluated against the state the
  conversation had before being greeted

#### Scenario: A claimed conversation is not answered by a FAQ

- **WHEN** an employee has claimed the conversation and the customer writes a question matching a
  FAQ
- **THEN** no FAQ is sent

### Requirement: Every automatic message is emitted at most once

The system SHALL record an emission key for each automatic message — the conversation for the
greeting, the pair of order and customer-facing state for status messages, and the pair of
conversation and FAQ for keyword replies — and SHALL NOT send a message whose key has already been
recorded. The record SHALL be written atomically so that concurrent attempts result in exactly one
send.

#### Scenario: A bouncing status does not message twice

- **WHEN** an order returns to a state whose message was already sent
- **THEN** no second message is sent

#### Scenario: Concurrent attempts send once

- **WHEN** two workers process the same transition at the same time
- **THEN** exactly one message is sent

#### Scenario: A retried event is not a second message

- **WHEN** the same transition notification is delivered more than once
- **THEN** the customer receives one message

#### Scenario: The same question twice gets one answer

- **WHEN** a customer asks the same FAQ's question twice in the same conversation
- **THEN** the FAQ is sent once

#### Scenario: A different question is still answered

- **WHEN** a customer asks about the address and then about the opening hours
- **THEN** both FAQs are sent, each once

### Requirement: Tenant-level autoreply settings

The system SHALL store, per tenant, the greeting text in its open and closed variants, whether
the greeting is enabled, whether the assistant is offered, the conversation idle window, the
store token lifetime, the mapping of transitions to customer messages, and the ordered list of
keyword FAQs. With the greeting disabled, the mapping empty and no FAQ enabled, the channel SHALL
behave exactly as it did without this capability.

Each FAQ SHALL carry a stable identifier, a name, an enabled flag, its triggers and its text. FAQ
texts SHALL be validated when saved, with the same placeholder rules and the same error style as the
greeting.

An absent FAQ list and an empty FAQ list SHALL mean different things: absent means the tenant has
never configured them, and the suggested FAQs SHALL be offered — **disabled** — so that installing
this capability changes no tenant's behaviour; empty means the tenant decided to have none, and none
SHALL be offered.

#### Scenario: Settings drive the behaviour

- **WHEN** a tenant edits the greeting text and the transition mapping
- **THEN** subsequent greetings and status messages use the new values

#### Scenario: Fully disabled is inert

- **WHEN** the greeting is disabled, the mapping is empty and no FAQ is enabled
- **THEN** no automatic message is ever emitted, and conversations are answered only by humans

#### Scenario: A tenant who never configured FAQs sees the suggestions

- **WHEN** a tenant that has never saved FAQs opens the settings
- **THEN** the suggested FAQs are present and disabled, and no FAQ answers until one is enabled

#### Scenario: A deleted FAQ does not come back

- **WHEN** a tenant deletes every FAQ and saves
- **THEN** no FAQ is offered again on the next read, and none is answered
