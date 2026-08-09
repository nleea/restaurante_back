## MODIFIED Requirements

### Requirement: Outbound is only ever a reply

The outbound gateway SHALL refuse to send a **message** to any phone number that has no
`whatsapp_contact` with at least one inbound message. This SHALL be enforced inside the gateway, so
that every current and future caller is bound by it without performing its own check. The system
SHALL NOT initiate a conversation with anyone.

A **status** is not a message and is not addressed to a conversation: it does not appear in anyone's
thread, it does not await a reply, and it does not place a conversation in the inbox. It is therefore
not subject to the per-recipient refusal above, and it does not initiate a conversation.

The invariant is nevertheless preserved for statuses, and preserved **by construction of the
audience** rather than by a check at send time: a status audience SHALL contain only contacts with at
least one inbound message on the publishing branch. No code path SHALL publish a status to an
audience assembled any other way, and in particular the system SHALL NOT use the provider's own
contact list as an audience.

The provider's contact list is the alternative on offer and it is refused deliberately: it is a set of
unknown size, populated by the provider's own syncing, over which the system's opt-out and inactivity
window have no effect.

#### Scenario: Replying to a contact who wrote is allowed

- **WHEN** a message is sent to a contact who has at least one inbound message
- **THEN** the gateway sends it

#### Scenario: Messaging a phone that never wrote is refused

- **WHEN** a send is attempted to a phone number with no contact record, or to a contact with
  no inbound message
- **THEN** the gateway refuses and no message is transmitted

#### Scenario: The guarantee does not depend on the caller

- **WHEN** any code path obtains the gateway from the composition root and attempts an
  unsolicited send
- **THEN** it is refused, because only the guarded gateway is ever injected

#### Scenario: A status is not refused for having no single recipient

- **WHEN** a status is published to an audience of contacts who have all written to that branch
- **THEN** the gateway publishes it, because a status is not a directed message

#### Scenario: The provider's own contact list is never the audience

- **WHEN** a status is published
- **THEN** the audience is the one the system assembled from its own contacts, and the provider is
  never asked to broadcast to all of its known contacts

## ADDED Requirements

### Requirement: The gateway publishes a status as its own verb

The outbound gateway SHALL expose publishing a status as a distinct operation from sending a message
and from sending media, taking the composed card and an explicit list of recipient addresses. All
provider-specific detail — the URL shape, the authentication header, the field names, where the
accepted publication's identifier is found — SHALL remain confined to the bridge adapter.

Statuses SHALL be published through the same guarded gateway that every other outbound path uses, so
that reachability of the bridge is checked in one place for all three verbs.

#### Scenario: Publishing goes through the guard

- **WHEN** a status is published and the bridge is unreachable
- **THEN** the failure is reported the same way an unreachable bridge is reported for a message

#### Scenario: A misconfigured bridge is distinguishable from a transport failure

- **WHEN** the bridge is not configured at all and a status is published
- **THEN** the error says the bridge is not configured, not that it could not be contacted

#### Scenario: Provider detail does not leak

- **WHEN** the status verb is called
- **THEN** the caller passes a composed card and addresses, and nothing about the provider's request
  shape

### Requirement: A contact can opt out of statuses

A contact SHALL carry an opt-out flag for statuses, defaulting to not opted out, and a contact who
has opted out SHALL be excluded from every status audience of the business.

The flag SHALL belong to the contact, not to a conversation: "stop sending me these" is addressed to
the business, and requiring the person to repeat it to each branch is how a number gets blocked
instead.

Opting a contact out SHALL NOT alter their conversations, their history, or their reachability for
replies.

#### Scenario: An opted-out contact receives no statuses

- **WHEN** a contact has opted out and a status is published from any branch
- **THEN** that contact is not in the audience

#### Scenario: Opting out does not affect replies

- **WHEN** a contact has opted out and then writes again
- **THEN** the thread behaves exactly as before and can be replied to

#### Scenario: Existing contacts are not opted out

- **WHEN** the opt-out flag is introduced
- **THEN** every existing contact is not opted out, and no behaviour changes for anyone until a
  status is created

#### Scenario: Opting out requires attending the inbox

- **WHEN** a user without `messaging.attend` attempts to change a contact's opt-out
- **THEN** the request is refused

### Requirement: The status candidate query is scoped to the publishing branch

The repository SHALL expose a query returning the status **candidates** for one branch: every contact
with at least one inbound message on that branch, each carrying its address, its most recent inbound
timestamp on that branch, and whether it has opted out — ordered by most recent inbound message
first.

The query SHALL NOT itself apply the opt-out or inactivity exclusions. It reports the facts; the
exclusions and their counts happen in one place above it. Excluding inside the query would make the
per-reason counts unobtainable, and those counts are themselves a requirement — a screen that cannot
say *why* an audience fell from 340 to 200 presents a truncated audience as a complete one.

Ordering is part of the requirement, not a convenience: it is what makes the recipient cap keep the
most recently engaged contacts rather than an arbitrary subset.

"Most recent inbound" SHALL be measured on inbound messages only. A reply the business sent
yesterday says nothing about whether that person is still there.

This query SHALL be distinct from the existing per-phone reachability check, which is deliberately
not branch-scoped and remains correct for directed messages.

#### Scenario: Candidates are ordered by recency

- **WHEN** the status candidates are read for a branch
- **THEN** contacts appear most-recently-inbound first

#### Scenario: Opt-out travels as a fact, not as a filter

- **WHEN** a contact of that branch has opted out
- **THEN** they appear among the candidates marked as opted out, so the exclusion can be counted

#### Scenario: Recency ignores outbound messages

- **WHEN** a contact's last inbound message is old but the business replied recently
- **THEN** the candidate's most recent inbound timestamp is the old one

#### Scenario: Reachability for messages is unchanged

- **WHEN** a contact wrote to branch B and a direct message is sent to them from branch A
- **THEN** the existing behaviour applies unchanged, because reachability for a message is a property
  of the business

### Requirement: Status emissions share the single-column emission key

The emission claimed before publishing a status SHALL use the existing single-text-column unique
emission mechanism, alongside greeting, order-state and payment-request keys.

#### Scenario: A status key coexists with the other kinds

- **WHEN** a status emission is claimed
- **THEN** it is stored in the same table under its own kind, and does not collide with greeting or
  order-state keys
