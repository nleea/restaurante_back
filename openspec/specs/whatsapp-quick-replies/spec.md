# whatsapp-quick-replies

## Purpose

Las plantillas de texto por tenant que un empleado inserta en el compositor del inbox: su forma,
su validación al guardar, la semilla de sugeridas y el camino de lectura para quien atiende.

Capability propia y **no** parte de `whatsapp-autoreply`, con la que comparte fila en la base de
datos y nada más: aquélla describe cuándo y qué contesta el sistema **solo**, y aquí el sistema no
contesta. Ninguna de sus defensas —gates de estado, gate de pedido vivo, emisión única, vocabulario
reservado— aplica cuando el mensaje lo manda una persona.

## Requirements
### Requirement: Quick replies are stored per tenant as an ordered list

The system SHALL store, for each tenant, an ordered list of quick replies, where each entry has a
stable `id`, a short `name` and a `text` body. The list order SHALL be the order in which the
entries are presented to staff. Quick replies SHALL NOT carry an enabled flag or trigger words:
they never fire on their own, so there is nothing to enable and nothing to match.

#### Scenario: Saving preserves order

- **WHEN** a manager saves the list `[A, B, C]`
- **THEN** a subsequent read returns exactly `[A, B, C]` in that order

#### Scenario: Reordering is persisted

- **WHEN** a manager moves `C` above `B` and saves
- **THEN** a subsequent read returns `[A, C, B]`

#### Scenario: Entries are scoped to the tenant

- **WHEN** tenant *A* has quick replies and tenant *B* has none
- **THEN** reading tenant *B*'s quick replies returns the unconfigured state, never tenant *A*'s
  entries

### Requirement: Never configured is distinct from deliberately empty

The system SHALL distinguish "this tenant has never configured quick replies" (stored as `null`)
from "this tenant decided to have none" (stored as an empty list). A tenant in the unconfigured
state SHALL be offered the suggested quick replies; a tenant that saved an empty list SHALL NOT be
offered them again.

#### Scenario: A tenant that never touched them sees suggestions

- **WHEN** a tenant that has never saved quick replies opens the editor
- **THEN** the suggested quick replies are offered

#### Scenario: Deleting them all is remembered

- **WHEN** a manager deletes every quick reply and saves
- **THEN** the stored value is an empty list, and reopening the editor offers no entries and does
  not resurrect the deleted ones

#### Scenario: Suggestions are inert until saved

- **WHEN** the suggested quick replies are offered to an unconfigured tenant
- **THEN** nothing is stored until the manager saves, and no message is sent to any customer as a
  result of the suggestions existing

### Requirement: Quick reply text is validated on save

The system SHALL reject a save when any quick reply has an empty name, an empty text, a name or
text longer than the configured limits, a duplicate `id`, or when the list exceeds the maximum
number of entries. Rejection SHALL be reported as a validation error that names the offending
entry, and SHALL leave the previously stored list untouched.

#### Scenario: Empty text is rejected

- **WHEN** a manager saves a quick reply whose text is blank
- **THEN** the request fails validation and the previously stored list is unchanged

#### Scenario: Duplicate identifiers are rejected

- **WHEN** a manager saves two quick replies sharing the same `id`
- **THEN** the request fails validation and the previously stored list is unchanged

#### Scenario: Too many entries are rejected

- **WHEN** a manager saves more quick replies than the maximum allowed
- **THEN** the request fails validation and the previously stored list is unchanged

### Requirement: Quick reply text may not contain placeholders

The system SHALL reject a save when a quick reply text contains a placeholder marker in braces.
Quick reply text is inserted verbatim into the composer and is never interpolated, so a stored
marker would reach the customer with its braces intact.

#### Scenario: A known autoreply marker is rejected

- **WHEN** a manager saves a quick reply whose text contains `{link}`
- **THEN** the request fails validation with a message explaining that quick replies do not
  interpolate markers

#### Scenario: An invented marker is rejected too

- **WHEN** a manager saves a quick reply whose text contains `{nombre}`
- **THEN** the request fails validation, because the failure mode does not depend on the marker
  being one the system knows

### Requirement: Staff who attend conversations can read the quick replies

The system SHALL expose the tenant's quick replies to any user holding the permission to attend
conversations, independently of the permission required to edit them. Editing SHALL continue to
require the messaging management permission.

#### Scenario: An agent without management permission can read them

- **WHEN** a user with `messaging.attend` but not `messaging.manage` requests the quick replies
- **THEN** the list is returned

#### Scenario: An agent without management permission cannot edit them

- **WHEN** a user with `messaging.attend` but not `messaging.manage` attempts to save quick replies
- **THEN** the request is denied

#### Scenario: A read-only user cannot read them

- **WHEN** a user with only `messaging.read` requests the quick replies
- **THEN** the request is denied, because the list only exists to be inserted into a reply

### Requirement: Quick replies never produce an outbound message on their own

The system SHALL NOT send, schedule, or queue any message as a consequence of a quick reply
existing, being read, or being selected. A quick reply reaches a customer only through the normal
staff reply path, which requires an explicit send by a person.

#### Scenario: Reading the list sends nothing

- **WHEN** the quick replies are read for a conversation
- **THEN** no outbound message is emitted and the conversation state is unchanged

#### Scenario: Selection alone sends nothing

- **WHEN** a staff member selects a quick reply and does not press send
- **THEN** no outbound message is emitted
