# whatsapp-autoreply

## Purpose

Las cuatro respuestas de WhatsApp que un restaurante da siempre igual y que no deberían esperar
a que alguien esté libre: el primer saludo con el enlace de la carta y el horario, el
comprobante del pedido, el «va en camino», y las preguntas que llegan todos los días —dónde
están, a qué hora, cómo se paga, si llevan a domicilio—. Ninguna necesita un modelo — son texto
determinista sobre datos que el sistema ya tiene (`is_open_at` / `next_opening` y el ciclo de
vida del pedido), así que esto es lo que el dueño enseña orgulloso y cuesta cero tokens.

Las FAQs por palabra clave son la cuarta y la única que **lee lo que el cliente escribió**, lo
que las obliga a justificarse: el saludo no lee el texto a propósito (ver más abajo), y una lista
de palabras clave es una fábrica de bugs si se usa para decidir la primera respuesta. Lo que las
hace defendibles son tres propiedades, y ninguna es opcional: coincidencia por palabra o frase
completa (`pago` no encuentra "ya pagué"), silencio cuando el contacto tiene un pedido vivo o
pide una persona (`direccion` no contesta a "mi dirección es la calle 5"), y que contestar **no
cambie el estado de la conversación ni la saque de la bandeja** — así una coincidencia equivocada
es un mensaje bochornoso y no un cliente perdido.

Dos invariantes lo sostienen. **Nada de aquí puede iniciar una conversación**: el saludo es
una respuesta, así que la regla del canal se cumple sola y a quien nunca escribió no le llega
nada. Y **cada mensaje automático se emite como mucho una vez**: el saludo deduplicado por
conversación, los estados por `(pedido, estado de cara al cliente)`, para que un rebote
`confirmado → en espera → confirmado` o un reintento no le escriba dos veces al cliente. El
techo de cuatro mensajes por pedido del mapeo por defecto no es pereza: es la defensa
principal contra que marquen el número.

El enlace tokenizado es además lo que ata un pedido web a la persona que escribió por
WhatsApp: el token opaco viaja en el enlace, el checkout rellena con él, y el pedido queda
enlazado al contacto para poder mandarle el comprobante.

Fuera de alcance: las alertas al personal (`alert-notifications`), cualquier cosa con un LLM
(`assistant-core`), mensajes con multimedia y tomar el pedido conversando.

## Requirements

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

### Requirement: The assistant is offered only when it will answer

The greeting SHALL offer the conversational assistant only when the tenant has it enabled **and the
branch is open**. When either condition fails, the greeting SHALL omit the offer, and a customer
asking to talk to someone SHALL be routed to the human inbox rather than to an assistant.

The hours condition is not a second rule but the same one: the schedule switches the assistant off,
so a closed greeting that says "write 1" leaves a customer writing a 1 at eleven at night that
neither the bot nor a person will answer — which is exactly what the offer exists to avoid.

#### Scenario: No assistant, no offer

- **WHEN** a tenant without the assistant enabled emits a greeting
- **THEN** the message does not offer to talk to an assistant

#### Scenario: Assistant enabled and open, offer present

- **WHEN** a tenant with the assistant enabled emits a greeting while the branch is open
- **THEN** the message offers it alongside the store link

#### Scenario: Closed, no offer

- **WHEN** that same tenant emits a greeting while the branch is closed
- **THEN** the message states the next opening and does not offer the assistant

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
greeting, the pair of order and customer-facing state for status messages, and the pair of
conversation and FAQ for keyword replies — and SHALL NOT
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

#### Scenario: The same question twice gets one answer

- **WHEN** a customer asks the same FAQ's question twice in the same conversation
- **THEN** the FAQ is sent once

#### Scenario: A different question is still answered

- **WHEN** a customer asks about the address and then about the opening hours
- **THEN** both FAQs are sent, each once

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
