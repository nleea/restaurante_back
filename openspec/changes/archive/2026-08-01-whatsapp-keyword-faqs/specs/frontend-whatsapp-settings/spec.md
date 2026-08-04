## ADDED Requirements

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
