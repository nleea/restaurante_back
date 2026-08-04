# frontend-whatsapp-settings

## Purpose

La pantalla por tenant donde se edita lo que el número contesta solo: el saludo en sus dos
variantes (abierto y cerrado), **qué transiciones de un pedido le escriben al cliente** — un
restaurante de sólo recogida quiere avisar de `listo` y uno de sólo domicilio no lo quiere nunca,
así que el mapeo se elige, no se hereda—, **las preguntas frecuentes por palabra clave**, y la
ventana de inactividad de la conversación junto a la vida del enlace tokenizado.

El interruptor del asistente sólo se puede tocar cuando el tenant tiene el derecho: ofrecer
algo que no existe todavía es peor que no ofrecerlo.

La sección de FAQs carga con una obligación que las otras tres no tienen: **decir cuándo NO
contesta**. Es el único mecanismo que reacciona a lo que el cliente escribe, y sus silencios
—pedido en curso, petición de una persona, primer mensaje de la conversación— son invisibles desde
fuera. Sin explicarlos, el dueño prueba la función escribiéndose a sí mismo con un pedido de prueba
abierto, no recibe nada y concluye que está roto.

## Requirements

### Requirement: Greeting settings screen

The front SHALL expose a per-tenant WhatsApp automation settings screen, gated on
`messaging.manage`, where the greeting can be enabled or disabled and its open and closed
variants edited. The editor SHALL list the available placeholders and SHALL show a live
preview rendered for a chosen branch, in both its open and closed forms.

#### Scenario: Editing the greeting

- **WHEN** a user with `messaging.manage` edits the greeting text and saves
- **THEN** subsequent greetings use the new text

#### Scenario: Preview shows both variants

- **WHEN** the editor is open with a branch selected
- **THEN** the open and closed renderings are both shown, with that branch's link and next
  opening substituted

#### Scenario: Unknown placeholder is rejected

- **WHEN** the text uses a placeholder that does not exist
- **THEN** saving is refused with a clear message naming the offending placeholder

#### Scenario: Disabling the greeting

- **WHEN** the greeting is disabled
- **THEN** the screen makes clear that new conversations will wait for a human

### Requirement: Status message mapping editor

The screen SHALL let the tenant choose which order and delivery transitions send a customer
message, and edit each message's text. It SHALL indicate how many messages a typical order
will produce under the current mapping, and SHALL warn when that count grows beyond the
recommended default.

#### Scenario: Opting into a transition

- **WHEN** the tenant enables the kitchen `ready` transition
- **THEN** subsequent ready events message the customer

#### Scenario: Message count is visible

- **WHEN** the mapping is edited
- **THEN** the screen shows how many messages a typical order will now send

#### Scenario: Chatty mapping is warned about

- **WHEN** the tenant enables enough transitions to exceed the recommended count
- **THEN** the screen warns that high outbound volume risks the WhatsApp number

### Requirement: Conversation and token settings

The screen SHALL expose the conversation idle window and the store token lifetime, explaining
that the idle window is what decides when a returning customer is greeted again.

#### Scenario: Editing the idle window

- **WHEN** the idle window is changed and saved
- **THEN** conversations close and re-greet on the new window

#### Scenario: Editing the token lifetime

- **WHEN** the token lifetime is changed and saved
- **THEN** newly minted store links carry the new lifetime

### Requirement: Assistant offer toggle reflects entitlement

The screen SHALL let the tenant choose whether the greeting offers the conversational
assistant, and SHALL disable that toggle with an explanation when the tenant has no assistant
enabled — so the greeting can never advertise something that will not answer.

With the offer turned on, the preview SHALL show the offer line **on the open variant only**, and
SHALL state on the closed variant why it is absent. The preview cannot show an offer the send does
not make: the closed greeting omits it because the schedule switches the assistant off.

#### Scenario: Toggle unavailable without the assistant

- **WHEN** the tenant has no assistant enabled
- **THEN** the offer toggle is disabled and explains why

#### Scenario: Toggle available with the assistant

- **WHEN** the tenant has the assistant enabled
- **THEN** the offer can be turned on and the open preview shows the offer line

#### Scenario: The closed preview does not promise the assistant

- **WHEN** the offer is turned on
- **THEN** the closed preview omits the offer line and says why it is absent outside opening hours

### Requirement: Keyword FAQ editor

The settings screen SHALL expose a fourth section where the tenant edits the ordered list of keyword
FAQs, gated on the same `messaging.manage` permission as the rest of the screen. Each FAQ SHALL be a
collapsible card showing its position, its name and an enabled toggle, and expanding to edit its
triggers as removable chips and its text as a textarea. The section SHALL allow adding a FAQ,
deleting one with confirmation, and restoring the suggested set with confirmation because it
discards edits.

FAQ texts SHALL be validated against the available placeholders while typing, with the same
treatment the greeting and the status messages already get: the offending placeholder is named and
saving is disabled until it is fixed. The server's refusal remains the judge.

#### Scenario: Editing a FAQ

- **WHEN** a user with `messaging.manage` edits a FAQ's triggers and text and saves
- **THEN** subsequent matching messages are answered with the new text

#### Scenario: Adding a FAQ requires the essentials

- **WHEN** a new FAQ is added without a name, without any trigger, or without text
- **THEN** saving is not possible until all three are present

#### Scenario: An unknown placeholder is named

- **WHEN** a FAQ's text uses a placeholder that does not exist
- **THEN** the section names it and saving is disabled

#### Scenario: A reserved trigger is reported

- **WHEN** saving is refused because a trigger contains a word reserved by the channel
- **THEN** the screen shows the server's explanation, naming the trigger and the reserved word

#### Scenario: Restoring the suggested set is confirmed

- **WHEN** the tenant restores the suggested FAQs
- **THEN** a confirmation states that the current list will be replaced

#### Scenario: Deleting every FAQ sticks

- **WHEN** the tenant deletes all FAQs and saves
- **THEN** reloading the screen shows an empty list, not the suggested set again

### Requirement: FAQ priority is reordered without dragging

The section SHALL let the tenant change a FAQ's priority with explicit move-up and move-down
controls, without a drag-and-drop dependency, and SHALL show each FAQ's position so that the list
order is legible as the matching priority. The controls SHALL be operable by keyboard and by touch,
SHALL be disabled at the ends of the list, and SHALL keep focus on the moved FAQ's control after a
move.

#### Scenario: Moving a FAQ changes priority

- **WHEN** the tenant moves a FAQ above another and saves
- **THEN** a message matching both is answered with the one now listed first

#### Scenario: Focus survives the move

- **WHEN** a FAQ is moved to the first position with the keyboard
- **THEN** focus stays on that FAQ's controls rather than being lost

#### Scenario: The ends are inert

- **WHEN** the first FAQ is displayed
- **THEN** its move-up control is disabled

### Requirement: The editor states when a FAQ stays silent

The section SHALL explain, in the screen itself, the conditions under which a FAQ does not answer:
while a customer has an order in progress, when the customer asks for a person or asks to cancel or
refund, on the very first message of a conversation (which the greeting owns), and inside a
conversation already taken by an employee or by the assistant. It SHALL also state that FAQs do
answer outside opening hours.

Without this, a tenant testing the feature against their own number while a test order is open
concludes it is broken.

#### Scenario: The silence conditions are visible

- **WHEN** the FAQ section is open
- **THEN** it states that FAQs do not answer over an order in progress, nor when a person is asked
  for, nor on the first message of a conversation

#### Scenario: Answering while closed is stated

- **WHEN** the FAQ section is open
- **THEN** it states that FAQs answer whether the business is open or closed

### Requirement: Permission gating and navigation

The settings screen SHALL require `messaging.manage`, SHALL be hidden from navigation without
it, and SHALL refuse direct entry.

#### Scenario: Hidden without permission

- **WHEN** a user without `messaging.manage` is signed in
- **THEN** the settings entry is absent from navigation and direct entry is refused

### Requirement: The settings screen edits quick replies

The WhatsApp settings screen SHALL provide a section for managing quick replies, listing each
entry with its name and text, allowing entries to be created, edited, deleted and reordered, and
saving them together with the rest of the autoreply settings.

#### Scenario: Creating an entry

- **WHEN** a manager adds a quick reply, fills in its name and text and saves
- **THEN** the entry is persisted and shown on the next load

#### Scenario: Reordering an entry

- **WHEN** a manager moves an entry up or down
- **THEN** the displayed order changes and the new order is what gets saved

#### Scenario: Deleting an entry

- **WHEN** a manager deletes an entry and saves
- **THEN** the entry is gone on the next load and does not reappear

### Requirement: The section explains that quick replies do not answer by themselves

The quick replies section SHALL state that these texts are inserted by a person into the composer
and are never sent automatically, so a manager does not confuse them with the keyword FAQs shown
elsewhere on the same screen.

#### Scenario: The distinction is visible without opening an entry

- **WHEN** a manager opens the quick replies section
- **THEN** help text states that quick replies never reply on their own

### Requirement: Suggested quick replies can be seeded

When the tenant has never configured quick replies, the section SHALL offer a set of suggested
entries and an explicit action to adopt them. Adopting them SHALL fill the editor without saving,
so the manager can edit or discard them before committing.

#### Scenario: Suggestions are offered to an unconfigured tenant

- **WHEN** a tenant that has never saved quick replies opens the section
- **THEN** the suggested entries are offered together with an action to adopt them

#### Scenario: Adopting does not save by itself

- **WHEN** a manager adopts the suggestions and leaves without saving
- **THEN** nothing is persisted and the tenant is still unconfigured

### Requirement: Invalid quick replies are reported before saving

The section SHALL block saving and explain the problem when a quick reply has an empty name, an
empty text, a text over the length limit, or a placeholder marker in braces.

#### Scenario: A placeholder is caught in the editor

- **WHEN** a manager types `{link}` into a quick reply text
- **THEN** the section reports that quick replies do not interpolate markers and saving is blocked

#### Scenario: An over-long text is caught in the editor

- **WHEN** a quick reply text exceeds the length limit
- **THEN** the section reports it and saving is blocked
