## ADDED Requirements

### Requirement: Open alerts are reminded until they are dealt with

An alert that stays `fired` SHALL be notified again every `remind_every_minutes` of its rule, so
that an alert nobody happened to be looking at when it first fired is not lost. A rule whose
interval is zero SHALL never remind, which is the behaviour of a system without this feature.

#### Scenario: An untouched alert is reminded

- **WHEN** an alert has been `fired` for longer than its rule's reminder interval and nobody has
  dealt with it
- **THEN** it is notified again

#### Scenario: Reminding does not create a second alert

- **WHEN** an alert is reminded
- **THEN** it remains the same single open alert, with its original firing time unchanged

#### Scenario: A zero interval never reminds

- **WHEN** a rule's reminder interval is zero
- **THEN** its alerts are notified once and never reminded

#### Scenario: A reminder is distinguishable from a first notification

- **WHEN** a reminder is sent
- **THEN** the notification says it is a reminder, so nobody reads it as a new problem

### Requirement: Three exits stop the reminders

Reminders SHALL stop when any of three things happens: the alert is acknowledged, the condition
resolves, or the alert's reminders are silenced. No other state SHALL suppress them.

#### Scenario: Acknowledging stops the reminders

- **WHEN** an alert is acknowledged
- **THEN** it is no longer reminded, even though it stays open

#### Scenario: Resolving stops the reminders

- **WHEN** the condition clears and the alert resolves
- **THEN** it is no longer reminded

#### Scenario: Silencing stops the reminders

- **WHEN** an alert's reminders are silenced
- **THEN** it is no longer reminded while it stays open, and it is still an open, unacknowledged
  alert

### Requirement: Silencing is per alert and dies with it

Silencing SHALL apply to one alert, never to its rule, and SHALL last only while that alert is
open. When the condition resolves and later fires again, the new alert SHALL remind normally.

#### Scenario: Silencing one alert leaves its siblings alone

- **WHEN** one subject's alert is silenced
- **THEN** other open alerts of the same rule keep being reminded

#### Scenario: A new alert after resolution reminds again

- **WHEN** a silenced alert resolves and the condition fires again later
- **THEN** the new alert is reminded normally

#### Scenario: Silencing does not claim ownership

- **WHEN** an alert is silenced
- **THEN** it is not recorded as acknowledged and nobody is recorded as having taken it

### Requirement: In-app reminders never reach the escalation channel

A reminder SHALL be delivered only through the always-on in-app channel. Repetition on the
escalation channel SHALL follow its own, far slower cadence and SHALL NOT be driven by the
reminder interval.

#### Scenario: A reminder is not an escalation

- **WHEN** an alert is reminded in-app
- **THEN** no message is sent through the escalation channel because of that reminder

#### Scenario: Reminders continue with no escalation channel configured

- **WHEN** no escalation channel is configured
- **THEN** reminders are still delivered in-app

### Requirement: A reminder is claimed before it is sent

Sending a reminder SHALL be claimed with a conditional update, so two concurrent evaluations of
the same alert produce at most one reminder.

#### Scenario: Concurrent sweeps remind once

- **WHEN** two evaluations of the same due alert run concurrently
- **THEN** exactly one reminder is sent

#### Scenario: An alert is not reminded again before its interval

- **WHEN** an alert was reminded less than its interval ago
- **THEN** no further reminder is sent

### Requirement: The reminder interval cannot beat the sweep

The effective reminder cadence SHALL be bounded below by the sweep cadence, because the sweep is
what evaluates due reminders. A configured interval shorter than the sweep SHALL behave as the
sweep cadence rather than being rejected.

#### Scenario: A too-short interval degrades to the sweep cadence

- **WHEN** a rule's reminder interval is shorter than the sweep interval
- **THEN** reminders arrive at the sweep cadence and nothing errors

## MODIFIED Requirements

### Requirement: Delayed escalation

An alert that remains unacknowledged for its rule's escalation delay SHALL be escalated. It SHALL
then be escalated again, at a fixed cadence defined by the system rather than by any rule, for as
long as it stays unacknowledged, unresolved and unsilenced. Each escalation SHALL be recorded so
the cadence can be enforced. Escalation to WhatsApp SHALL respect the channel's outbound invariant.

The re-escalation cadence SHALL NOT be configurable per rule: it bounds a risk borne by the
business's phone number, not by the rule.

#### Scenario: Unacknowledged alerts escalate on the delay

- **WHEN** an alert is unacknowledged past its escalation delay
- **THEN** it is escalated and the escalation is recorded

#### Scenario: A still-ignored alert escalates again later

- **WHEN** an escalated alert is still unacknowledged after the re-escalation cadence has passed
- **THEN** it is escalated again

#### Scenario: Escalation does not repeat before its cadence

- **WHEN** an alert was escalated more recently than the re-escalation cadence
- **THEN** it is not escalated again

#### Scenario: The three exits stop escalation too

- **WHEN** an escalated alert is acknowledged, resolved or silenced
- **THEN** it is not escalated again

#### Scenario: Escalation cannot message an unreachable employee

- **WHEN** escalation would message an employee with no WhatsApp contact who wrote first
- **THEN** no message is sent and the escalation is still recorded

### Requirement: Alert rules are configured per branch

The system SHALL hold, per branch, a configuration for each known rule: whether it is enabled,
its threshold where the rule defines one, its recovery buffer, **its reminder interval**, its
escalation delay, and whether it escalates to WhatsApp. Rules SHALL be seeded disabled, so nothing
fires until a tenant enables it. Rule conditions SHALL be defined in code, not authored by users.

#### Scenario: A disabled rule never fires

- **WHEN** a rule is disabled for a branch and its condition becomes true
- **THEN** no alert is fired for that branch

#### Scenario: Configuration is per branch

- **WHEN** a rule is enabled for one branch and disabled for another in the same tenant
- **THEN** only the enabled branch fires alerts for it

#### Scenario: Rules arrive disabled

- **WHEN** a tenant is provisioned
- **THEN** every rule is present and disabled

#### Scenario: The reminder interval is part of the rule

- **WHEN** a manager saves a rule with a reminder interval
- **THEN** that interval governs how often its open alerts are reminded
