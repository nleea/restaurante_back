## ADDED Requirements

### Requirement: An order awaiting its receipt says so, instead of being acknowledged twice

A prepaid order with no payment registered SHALL be acknowledged with a message stating that the
order is held and enters the kitchen once the receipt is seen, **replacing** the ordinary "we
received your order" message rather than being sent in addition to it. Its text SHALL be editable by the tenant like every other automatic message, and it SHALL be
able to carry the order's number, total and itemised detail.

Sending both messages SHALL be treated as a defect: it is the same fact twice, and the ceiling of
four messages per order is the channel's main defence against the number being flagged.

#### Scenario: A prepaid, unsettled order is told what is missing

- **WHEN** an order is placed with a non-cash method and no payment registered
- **THEN** the customer receives the awaiting-receipt message and does not receive the ordinary
  acknowledgement

#### Scenario: A cash order is unaffected

- **WHEN** an order is placed to be paid in cash
- **THEN** the customer receives the ordinary acknowledgement, as before

#### Scenario: The ceiling holds

- **WHEN** a prepaid order runs its whole life with the default mapping
- **THEN** the customer receives no more messages than a cash order does

#### Scenario: The tenant can edit it

- **WHEN** the tenant edits the awaiting-receipt text
- **THEN** subsequent prepaid orders use the new text, validated like any other

### Requirement: The greeting recognises a customer whose order awaits payment

The greeting SHALL use a third variant — one that names the order and asks for the receipt, instead
of the open or closed variant — when the first message of a conversation arrives from a contact that
has an unsettled prepaid order.

This variant SHALL be chosen by the **state of the order**, never by the content of the message. The
greeting SHALL remain unconditional with respect to what the customer wrote: a photo, a "hola" and a
sticker SHALL all produce the same greeting. Keyword detection remains out of the greeting.

The variant SHALL also be what puts the order's context into the thread, so that whoever opens the
conversation reads the order number and total above the file the customer sent.

#### Scenario: A receipt is not answered with a menu link

- **WHEN** a customer who ordered on the web, never wrote before, and owes payment sends their first
  message
- **THEN** the greeting names their order and asks for the receipt, rather than welcoming them to the
  menu

#### Scenario: The choice does not read the message

- **WHEN** that same customer's first message is a photo with no text, or an unrelated word
- **THEN** the same variant is used, because the choice depends on the order's state

#### Scenario: No unsettled order, no change

- **WHEN** the contact has no unsettled prepaid order
- **THEN** the open or closed variant is used exactly as before

#### Scenario: The thread carries the order context

- **WHEN** the variant is sent
- **THEN** the order's number and total are in the thread, visible to whoever attends it

## MODIFIED Requirements

### Requirement: Tenant-level autoreply settings

The system SHALL store, per tenant, the greeting text in its open and closed variants, whether
the greeting is enabled, whether the assistant is offered, the conversation idle window, the
store token lifetime, the mapping of transitions to customer messages, and the ordered list of
keyword FAQs. With the greeting disabled, the mapping empty and no FAQ enabled, the channel SHALL
behave exactly as it did without this capability.

It SHALL additionally store the greeting's **awaiting-payment** variant, used when the contact has an
unsettled prepaid order. An empty variant SHALL fall back to the open or closed text rather than
sending nothing.

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

#### Scenario: The awaiting-payment greeting is editable and optional

- **WHEN** the tenant leaves the awaiting-payment variant empty
- **THEN** a contact with an unsettled order receives the open or closed greeting, never silence
