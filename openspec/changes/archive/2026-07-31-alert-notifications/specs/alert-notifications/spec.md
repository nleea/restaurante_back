## ADDED Requirements

### Requirement: Alert rules are configured per branch

The system SHALL hold, per branch, a configuration for each known rule: whether it is enabled,
its threshold where the rule defines one, its recovery buffer, its escalation delay, and
whether it escalates to WhatsApp. Rules SHALL be seeded disabled, so nothing fires until a
tenant enables it. Rule conditions SHALL be defined in code, not authored by users.

#### Scenario: A disabled rule never fires

- **WHEN** a rule is disabled for a branch and its condition becomes true
- **THEN** no alert is fired for that branch

#### Scenario: Configuration is per branch

- **WHEN** a rule is enabled for one branch and disabled for another in the same tenant
- **THEN** only the enabled branch fires alerts for it

#### Scenario: Rules arrive disabled

- **WHEN** a tenant is provisioned
- **THEN** every rule is present and disabled

### Requirement: Alert lifecycle

An alert SHALL move through `armed`, `fired`, `acknowledged` and `resolved`, and SHALL return
to `armed` only after being resolved. At most one open alert SHALL exist per branch, rule and
subject at a time.

#### Scenario: A condition becoming true fires once

- **WHEN** a rule's condition becomes true for a subject in an `armed` state
- **THEN** exactly one alert is fired for that branch, rule and subject

#### Scenario: A firing condition that persists does not re-fire

- **WHEN** the condition remains true across several evaluations
- **THEN** the existing alert stays open and no further alert is fired

#### Scenario: Acknowledging does not resolve

- **WHEN** an alert is acknowledged while its condition is still true
- **THEN** it is `acknowledged` and remains open

#### Scenario: One open alert per subject

- **WHEN** the same subject would fire twice concurrently
- **THEN** exactly one open alert exists for it

### Requirement: Recovery hysteresis

An alert SHALL re-arm only when its condition has cleared past the rule's recovery buffer, not
merely when it returns to the threshold. The recovery buffer SHALL NOT be configurable to
zero.

#### Scenario: Returning to the threshold does not re-arm

- **WHEN** a low-stock alert's stock returns exactly to its minimum
- **THEN** the alert does not re-arm

#### Scenario: Clearing past the buffer re-arms

- **WHEN** stock rises above the minimum plus the recovery buffer
- **THEN** the alert resolves and the rule re-arms for that subject

#### Scenario: Oscillation produces one alert

- **WHEN** a value crosses the threshold repeatedly without ever clearing the buffer
- **THEN** exactly one alert was fired and no further notifications were sent

#### Scenario: Zero buffer is refused

- **WHEN** a rule is configured with a recovery buffer of zero
- **THEN** the configuration is rejected

### Requirement: Announced job for latency

A mutation that can make a rule's condition true SHALL announce an evaluation job for the
affected subject, so the alert fires within seconds rather than at the next sweep. The system
SHALL remain correct if the job is never enqueued, is lost, or fails.

#### Scenario: A stock movement evaluates promptly

- **WHEN** a stock movement takes an ingredient below its minimum
- **THEN** an evaluation is announced and the alert fires without waiting for the sweep

#### Scenario: A lost job does not lose the alert

- **WHEN** the job queue is unavailable when the mutation happens
- **THEN** the mutation still succeeds and the alert is fired by the next sweep

### Requirement: Cron sweep is the guarantee

A periodic sweep SHALL evaluate every enabled rule for every branch and fire whatever is due,
independently of any announced job. The sweep SHALL be authoritative: an alert SHALL be fired
by it whether or not a job was ever enqueued for the subject.

#### Scenario: The sweep finds what the job path missed

- **WHEN** a condition became true while the job path was unavailable
- **THEN** the next sweep fires the alert

#### Scenario: The sweep covers every tenant and branch

- **WHEN** the sweep runs
- **THEN** it evaluates enabled rules across all tenants and branches, not only recently active
  ones

#### Scenario: The sweep does not duplicate a job's work

- **WHEN** a job has already fired an alert for a subject
- **THEN** the sweep does not fire a second one

### Requirement: Firing is claimed atomically

The transition from `armed` to `fired` SHALL be atomic, so that concurrent evaluators — an
announced job and a sweep, or two sweeps — result in exactly one firing and exactly one
notification.

#### Scenario: Job and sweep race

- **WHEN** an announced job and a sweep evaluate the same subject simultaneously
- **THEN** exactly one alert is fired and one notification is sent

### Requirement: Notification through a port, in-app first

Notifications SHALL be delivered through a channel port. In-app realtime SHALL be used on
firing. WhatsApp SHALL be used only for escalation, and only when the rule enables it. The
capability SHALL function with no WhatsApp channel present at all.

#### Scenario: Firing notifies in-app

- **WHEN** an alert fires
- **THEN** a realtime notification is published for that tenant and branch

#### Scenario: Works without WhatsApp

- **WHEN** no WhatsApp channel is configured
- **THEN** alerts still fire, notify in-app, and can be acknowledged and resolved

#### Scenario: A channel outage does not lose the alert

- **WHEN** a notification channel is unavailable while an alert fires
- **THEN** the alert is still recorded as fired and appears in the alerts listing

### Requirement: Attributed acknowledgement

An alert SHALL be acknowledgeable by a user with the alerts permission, recording who
acknowledged it and when, and that attribution SHALL be visible to everyone who can see the
alert.

#### Scenario: Acknowledgement names the person

- **WHEN** a user acknowledges an alert
- **THEN** the alert records that user and the time, visible to others

#### Scenario: Acknowledging stops escalation

- **WHEN** an alert is acknowledged before its escalation delay elapses
- **THEN** it is not escalated

### Requirement: Delayed escalation

An alert that remains unacknowledged for its rule's escalation delay SHALL be escalated, and
escalation SHALL be recorded so it happens at most once per alert. Escalation to WhatsApp
SHALL respect the channel's outbound invariant.

#### Scenario: Unacknowledged alerts escalate once

- **WHEN** an alert is unacknowledged past its escalation delay
- **THEN** it is escalated exactly once and the escalation is recorded

#### Scenario: Escalation cannot message an unreachable employee

- **WHEN** escalation would message an employee with no WhatsApp contact who wrote first
- **THEN** no message is sent and the escalation is still recorded

### Requirement: Low stock rule

The system SHALL provide a low-stock rule evaluating a branch's stock against the existing
per-ingredient minimum, with the alert's subject being the ingredient. It SHALL NOT introduce a
second stock threshold alongside the existing minimum.

#### Scenario: Crossing the minimum fires

- **WHEN** an ingredient's stock falls below its configured minimum on an enabled branch
- **THEN** an alert fires naming that ingredient

#### Scenario: Each ingredient is its own subject

- **WHEN** two ingredients fall below their minimums
- **THEN** two alerts exist, one per ingredient

#### Scenario: No ingredient minimum, no alert

- **WHEN** an ingredient has no configured minimum
- **THEN** it never fires a low-stock alert

### Requirement: WhatsApp session down rule

The system SHALL provide a rule that fires when a branch's WhatsApp session is not connected,
so a mute branch is visible rather than silent.

#### Scenario: A disconnected branch fires

- **WHEN** a branch's WhatsApp session status is not connected while the rule is enabled
- **THEN** an alert fires for that branch

#### Scenario: Reconnecting resolves

- **WHEN** the session returns to connected
- **THEN** the alert resolves and the rule re-arms

#### Scenario: Rule is inert without the channel

- **WHEN** no WhatsApp sessions exist
- **THEN** the rule fires nothing

### Requirement: Cash session left open rule

The system SHALL provide a rule that fires when a branch still has an open cash session past a
configured hour, so a shift is not left open overnight.

#### Scenario: Open past the configured hour fires

- **WHEN** a branch's cash session is still open past the configured hour
- **THEN** an alert fires for that branch

#### Scenario: Closing resolves

- **WHEN** the cash session is closed
- **THEN** the alert resolves and the rule re-arms

### Requirement: Permission gating

Reading alerts SHALL require `alerts.read`; acknowledging SHALL require `alerts.read`;
configuring rules SHALL require `alerts.manage`.

#### Scenario: Read without permission

- **WHEN** a user lacking `alerts.read` calls an alerts read endpoint
- **THEN** the system responds 403 Forbidden

#### Scenario: Configure without permission

- **WHEN** a user lacking `alerts.manage` tries to change a rule's configuration
- **THEN** the system responds 403 Forbidden

#### Scenario: Reading does not grant configuring

- **WHEN** a user has `alerts.read` but not `alerts.manage`
- **THEN** they can list and acknowledge alerts but cannot change any rule
