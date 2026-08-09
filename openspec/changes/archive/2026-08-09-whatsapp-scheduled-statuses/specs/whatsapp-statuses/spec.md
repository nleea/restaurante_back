## ADDED Requirements

### Requirement: A status is a composed card, validated when it is saved

A status SHALL be either a **text card** — content, background colour and font — or an **image**
with an optional caption. For a text status, background colour and font SHALL be non-null, and the
system SHALL reject a status that lacks them **when it is saved**, not when it is published.

Validating at save time is the requirement, not an implementation note: a status is published by a
background worker at a scheduled minute with nobody watching, so a provider rejection discovered at
publish time is a failure the owner learns about from an empty phone.

An image SHALL be stored by the system and handed to the provider as a URL. The system SHALL NOT
transmit image bytes inline.

#### Scenario: A text status without a background colour is refused

- **WHEN** a text status is saved with no background colour or no font
- **THEN** it is rejected with a validation error naming what is missing, and nothing is stored

#### Scenario: A saved text status carries everything the provider requires

- **WHEN** a text status is saved with content, background colour and font
- **THEN** it is stored, and publishing it later cannot fail for a missing composition field

#### Scenario: An image status is published by reference

- **WHEN** an image status is published
- **THEN** the provider receives a URL to the stored image, and the caption if there is one

### Requirement: A schedule is a set of slots, and a slot is a weekday or a date, never both

A status SHALL carry zero or more slots. Each slot SHALL have a minute of the day expressed in
**minutes from midnight in the branch's local time**, and SHALL have **exactly one** of: a weekday
(0=Monday … 6=Sunday), or a single calendar date. A slot with both, or with neither, SHALL be
rejected.

There SHALL be no separate field declaring whether a status is one-off or recurring. The slots are
the schedule. A status with no slots SHALL never publish.

#### Scenario: Every day at the same time

- **WHEN** the owner schedules a status for every day at 11:00
- **THEN** it is stored as seven weekday slots at minute 660

#### Scenario: A single date

- **WHEN** the owner schedules a status for one specific date at 18:00
- **THEN** it is stored as one dated slot at minute 1080

#### Scenario: A slot cannot be both

- **WHEN** a slot is submitted with both a weekday and a date
- **THEN** it is rejected

#### Scenario: A past dated slot is inert without being switched off

- **WHEN** a status's only slot is a date that has already passed
- **THEN** it never publishes again, because only slots due today are ever considered

### Requirement: Times are the branch's local wall clock

Every comparison between a slot and the present moment SHALL use the branch's local time, including
the weekday. The system SHALL NOT derive the weekday or the minute of day from UTC.

This is a requirement and not a detail: in a UTC-5 branch, after 19:00 local the UTC date has already
rolled over, so a UTC weekday publishes **tomorrow's** schedule.

#### Scenario: An evening slot uses today's weekday

- **WHEN** a weekday slot is due at 20:00 local time in a UTC-5 branch
- **THEN** it is matched against the local weekday, not the UTC one, and publishes on the day the
  owner selected

### Requirement: The audience is the publishing branch's own inbound contacts

The audience for a status SHALL be built from contacts who have sent at least one inbound message
**to the branch that publishes it**. Contacts who wrote only to another branch of the same business
SHALL NOT be included.

A WhatsApp status is only visible to someone who has that number saved, so a contact of another
branch can never see this branch's status. Including them would be pure outbound volume with no
possible audience.

#### Scenario: A contact of the publishing branch is included

- **WHEN** a contact has written to branch A and a status is published from branch A
- **THEN** that contact is in the audience

#### Scenario: A contact of another branch is excluded

- **WHEN** a contact has written only to branch B and a status is published from branch A
- **THEN** that contact is not in the audience

#### Scenario: A contact who never wrote is excluded

- **WHEN** a contact record exists with no inbound message on that branch
- **THEN** that contact is not in the audience

### Requirement: The audience is reduced by four filters, and every reduction is reported

The audience SHALL be reduced, in order, by excluding: contacts whose address is a privacy JID;
contacts who have opted out of statuses; contacts with no inbound message within the inactivity
window; and finally, contacts beyond the recipient cap.

Each exclusion SHALL be reported as its own count, distinguishable from the others, both before
publishing and in the record of what was published. The system SHALL NOT report a reduced audience
as a complete one.

The inactivity window and the recipient cap SHALL be configurable, and the cap SHALL be bounded by
an absolute ceiling that configuration cannot exceed.

#### Scenario: The counts are itemised, not summed

- **WHEN** an audience of 340 contacts is reduced by 12 privacy JIDs, 4 opt-outs, 118 inactive and
  a cap of 200
- **THEN** each of those four numbers is reported separately, and the audience is 200

#### Scenario: Truncation by the cap is stated

- **WHEN** the cap removes recipients who passed every other filter
- **THEN** the number omitted is reported, and the outcome is never presented as reaching everyone

#### Scenario: The cap cannot be raised without limit

- **WHEN** configuration sets a recipient cap above the absolute ceiling
- **THEN** the ceiling applies

#### Scenario: Recipients are ordered by recency

- **WHEN** the cap must drop recipients
- **THEN** the ones kept are those who wrote most recently

### Requirement: Contacts reachable only by a privacy JID are excluded and counted

A contact whose stored address is a WhatsApp privacy JID rather than a phone number SHALL be
excluded from the audience and counted under its own label.

Such an address is the only way to message that contact directly, but whether it is accepted as a
status recipient is unverified, and a provider that discards a failed batch reports success anyway.
Excluding visibly is the required behaviour; including and failing silently is not, because a
failure that presents itself as a success cannot be diagnosed.

#### Scenario: A privacy-JID contact does not receive a status

- **WHEN** the audience contains a contact whose address is a privacy JID
- **THEN** that contact is excluded, and reported as having no visible number

#### Scenario: Ordinary numbers are addressed as full JIDs

- **WHEN** a contact's address is a phone number
- **THEN** it is sent to the provider as a fully-formed WhatsApp JID

### Requirement: A status publishes at most once per status, local date and minute

Before publishing, the system SHALL claim a unique emission keyed by the status, the **local
calendar date** and the **minute of day**. Only the claimant SHALL publish. The key SHALL NOT
include the identity of the slot row.

Slot rows are rewritten wholesale when a schedule is saved, so a key built on slot identity stops
matching after any edit — and every already-published status of that day publishes again. Keying on
the wall clock survives the rewrite and is the same for weekday and dated slots.

#### Scenario: Two sweeps in the same minute publish once

- **WHEN** the due-slot sweep runs twice for the same status, date and minute
- **THEN** exactly one publication happens

#### Scenario: Editing a status does not republish it

- **WHEN** a status published at 11:00 and its content or schedule is saved again at 11:05, leaving
  the 11:00 slot in place
- **THEN** it does not publish again that day

#### Scenario: Two slots on the same day are two publications

- **WHEN** a status has slots at 11:00 and 18:30 on the same day
- **THEN** it publishes twice, once per minute, because the minute is part of the key

#### Scenario: The same slot publishes again the next day

- **WHEN** a weekday slot is due on consecutive matching days
- **THEN** it publishes on each of them, because the local date is part of the key

### Requirement: A slot that came due too long ago is recorded as skipped, not published

When a due slot's minute passed more than the grace window ago, the system SHALL NOT publish it. It
SHALL record a skipped publication stating the slot's time and the reason, and SHALL claim the
emission so the slot is not reconsidered on the next sweep.

A WhatsApp status expires after 24 hours, so publishing the lunch menu in the afternoon because the
worker was down since morning is worse than not publishing it. Recording the skip is what makes not
publishing defensible: the outcome is an entry the owner can read, not silence.

#### Scenario: A late slot is skipped visibly

- **WHEN** the worker resumes and finds a slot that came due beyond the grace window
- **THEN** nothing is published, and a skipped publication is recorded with the slot's time

#### Scenario: A slot inside the window still publishes

- **WHEN** a slot came due within the grace window
- **THEN** it publishes normally

#### Scenario: A restart does not release a burst

- **WHEN** the worker restarts and several slots of the day are long overdue
- **THEN** none of them publish, and each is recorded as skipped

#### Scenario: A skipped slot is not reconsidered

- **WHEN** the sweep runs again after recording a skip
- **THEN** the slot is not evaluated again for that date and minute

### Requirement: Publishing is background work, and one publication is one call

Publishing SHALL be performed by background work, not within the request that schedules or triggers
it.

One publication SHALL be handed to the provider as a **single call carrying the whole recipient
list**. The system SHALL NOT split the audience into several calls.

Splitting is the intuitive choice and it is wrong: the provider batches internally and re-sends each
batch with the *same* message identifier, which is what makes every recipient see one story. A
publication split into N of our own calls would be N publications with N identifiers — 200
recipients would become 20 identical stories in each contact's updates tab.

The system SHALL pace itself between **separate publications** instead, with an irregular delay. Two
statuses due in the same minute are two bursts of provider calls, and back-to-back identical timing
is itself a signature.

The system SHALL be correct with the periodic sweep as its only path: there SHALL be no announcement
mechanism that the sweep depends on.

#### Scenario: A request does not carry the publication

- **WHEN** publishing is requested for a status
- **THEN** the request completes without transmitting to the provider, and the work is queued

#### Scenario: One publication is one provider call

- **WHEN** a status publishes to 200 recipients
- **THEN** the provider receives one call listing all 200, not twenty calls of ten

#### Scenario: Separate publications are paced apart

- **WHEN** two statuses are due at the same minute
- **THEN** an irregular delay separates the two publications

#### Scenario: The sweep alone is sufficient

- **WHEN** every optimisation path is removed and only the periodic sweep runs
- **THEN** every due slot still publishes within the grace window

### Requirement: The record states what was attempted, never what was seen

Every publication attempt SHALL be recorded with its status, its local date and minute, its outcome,
the number of recipients addressed, and the number excluded. When the provider accepts the
publication, its message identifier SHALL be stored.

The system SHALL NOT record, report or imply how many people viewed a status, nor that it was
delivered to anyone. The provider reports neither, and a partially failed batch is reported as
success, so the strongest available claim is that the bridge accepted the publication.

#### Scenario: An accepted publication is recorded as published

- **WHEN** the provider accepts a publication of 200 recipients
- **THEN** the record says published, addressed to 200, with the provider's identifier

#### Scenario: A rejected publication is recorded as failed

- **WHEN** the provider rejects the publication
- **THEN** the record says failed, and the status remains as it was

#### Scenario: An empty audience is its own outcome

- **WHEN** no contact survives the four reductions at the moment a slot comes due
- **THEN** nothing is published and the record says the audience was empty — distinctly from failed
  (nothing broke) and from published (nothing went out), carrying the four exclusion counts, which
  are the explanation of why there was nobody

#### Scenario: Views are never claimed

- **WHEN** any record or report of a publication is produced
- **THEN** it states how many recipients were addressed, and makes no statement about views or
  deliveries

### Requirement: A status publishes regardless of the branch's operating hours

The system SHALL publish a due status whether or not the branch is open, and SHALL NOT offer a
setting to restrict publishing to opening hours.

The weekday selector already expresses which days a status goes out; a second control over the same
fact could contradict it, and would do so by silently not publishing. A status makes no promise of
attention — it is a sign, not a conversation — which is why the rule that silences the assistant when
closed does not apply here.

#### Scenario: A status publishes on a closed day

- **WHEN** a status is due on a day the branch does not open
- **THEN** it publishes

#### Scenario: The owner excludes a day by not selecting it

- **WHEN** the owner does not want a status on Mondays
- **THEN** the way to express that is to leave Monday unselected, and no other setting affects it

### Requirement: Permission gating

Composing, scheduling and publishing statuses, and reading their publication records, SHALL require
`messaging.manage`.

#### Scenario: A user without the permission cannot manage statuses

- **WHEN** a user without `messaging.manage` attempts to read, create, schedule or publish a status
- **THEN** the request is refused
