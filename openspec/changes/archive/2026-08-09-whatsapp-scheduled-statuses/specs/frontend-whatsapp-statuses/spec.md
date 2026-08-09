## ADDED Requirements

### Requirement: Statuses screen and permission gating

The app SHALL provide a statuses screen for the current branch, reachable from the WhatsApp
navigation, gated by `messaging.manage`. A user without the permission SHALL NOT see the navigation
entry and SHALL NOT be able to reach the route.

The screen SHALL show the branch's statuses, each with its schedule and its most recent outcome.

#### Scenario: A manager reaches the screen

- **WHEN** a user with `messaging.manage` opens the WhatsApp section
- **THEN** the statuses entry is present and the screen lists the branch's statuses

#### Scenario: Without the permission the screen does not exist

- **WHEN** a user without `messaging.manage` is signed in
- **THEN** the navigation entry is absent and navigating to the route directly does not render it

### Requirement: The preview is the card that will be published

For a text status, the preview SHALL render the content using the **actual** background colour and
font that will be sent, in the proportions of a phone status. For an image status, the preview SHALL
render the image with its caption.

The preview cannot be an approximation: background colour and font are exactly the two parameters the
provider requires, so a preview that renders them differently is a preview that lies about the only
things it could get wrong.

#### Scenario: Changing the colour changes the preview

- **WHEN** the owner picks a background colour
- **THEN** the preview repaints in that colour

#### Scenario: Changing the font changes the preview

- **WHEN** the owner picks a font
- **THEN** the preview renders the content in it

#### Scenario: A text status cannot be saved without its card fields

- **WHEN** the owner tries to save a text status without a background colour or a font
- **THEN** saving is prevented and the missing field is named

### Requirement: The week shows which slots are taken

The schedule editor SHALL present the seven weekdays and let the owner place a time on any of them,
and SHALL let the owner place a time on a single specific date. It SHALL show the resulting slots
against the week so that occupied times are visible at a glance.

Selecting every weekday SHALL be the way to express "every day", and the interface SHALL NOT offer a
separate one-off/recurring mode.

#### Scenario: Every day at one time

- **WHEN** the owner selects all seven weekdays and a time
- **THEN** the schedule shows that time on every day

#### Scenario: Two times on one day

- **WHEN** the owner adds 11:00 and 18:30
- **THEN** both appear on the week, and both will publish

#### Scenario: A specific date

- **WHEN** the owner schedules a status for one date
- **THEN** it is shown as a dated slot, distinct from the weekly ones

#### Scenario: Times are the branch's local times

- **WHEN** a time is entered
- **THEN** it is presented and stored as the branch's local wall-clock time

### Requirement: The audience is counted and its reductions itemised before publishing

Before a status is scheduled or published, the screen SHALL show how many contacts will be addressed
and SHALL itemise each exclusion separately: contacts with no visible number, contacts who asked not
to receive statuses, inactive contacts, and contacts omitted by the cap.

The screen SHALL NOT show only the final number. A count presented without its exclusions reads as
full coverage of the business's contacts, which it is not.

#### Scenario: The reductions are visible, not summed

- **WHEN** the audience is 340 contacts reduced to 200
- **THEN** the screen shows the 200 and, separately, how many were dropped for each of the four
  reasons

#### Scenario: Truncation by the cap is called out

- **WHEN** the cap omits contacts who passed every other filter
- **THEN** the screen says how many are omitted

#### Scenario: An empty audience is explained

- **WHEN** no contact survives the filters
- **THEN** the screen says the status will reach nobody and why, rather than showing zero without a
  reason

### Requirement: The publication record says what happened without claiming views

The screen SHALL show, per status, its publication history: when it was attempted, whether it was
published, failed or skipped, how many recipients were addressed, and how many were excluded.

A publication that did not go out SHALL state which of the two reasons applies — the scheduled time
passed outside the window, or no contact survived the reductions — so that a status that did not go
out is never an unexplained absence.

The screen SHALL NOT display, imply or estimate how many people saw a status, nor that it was
delivered to anyone.

#### Scenario: A published status shows what was attempted

- **WHEN** a status published to 200 recipients
- **THEN** the record says published and addressed to 200

#### Scenario: A skipped status explains itself

- **WHEN** a scheduled time passed while the system was unable to publish
- **THEN** the record says the time was missed and the status was not published

#### Scenario: A failed status is distinguishable from a skipped one

- **WHEN** the provider rejected a publication
- **THEN** the record says failed, distinctly from a skipped one

#### Scenario: An empty audience is distinguishable from a missed time

- **WHEN** a status did not go out because nobody survived the reductions
- **THEN** the record says so, distinctly from one that missed its window

#### Scenario: No view counts anywhere

- **WHEN** any publication record is displayed
- **THEN** it makes no statement about views or deliveries

### Requirement: State is legible without colour alone

Each status's schedule state and each publication's outcome SHALL be distinguishable without relying
on colour alone, carrying a text or shape cue as well.

#### Scenario: Outcomes are readable in greyscale

- **WHEN** the publication history is rendered without colour
- **THEN** published, failed, missed-window and empty-audience remain distinguishable
