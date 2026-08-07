## ADDED Requirements

### Requirement: Alerts panel for the active branch

The front SHALL expose an alerts panel listing the open alerts of the active branch — what
fired, about which subject, when, and whether it is acknowledged and by whom. Alerts of other
branches SHALL NOT appear.

#### Scenario: Open alerts are listed

- **WHEN** a user with `alerts.read` opens the panel with a branch active
- **THEN** that branch's open alerts are listed with subject, time and acknowledgement state

#### Scenario: Acknowledged alerts show who took them

- **WHEN** an alert has been acknowledged
- **THEN** the panel shows which employee acknowledged it and when

#### Scenario: Resolved alerts leave the open list

- **WHEN** an alert resolves
- **THEN** it no longer appears among the open alerts

#### Scenario: Empty state

- **WHEN** the active branch has no open alerts
- **THEN** the panel shows an all-clear state rather than a blank panel

### Requirement: Acknowledging from the panel

A user with `alerts.read` SHALL be able to acknowledge an open alert from the panel. When
another user acknowledges first, the panel SHALL show the holder rather than silently
appearing unacknowledged.

#### Scenario: Acknowledging updates for everyone

- **WHEN** a user acknowledges an alert
- **THEN** it shows as acknowledged by them, in their panel and in everyone else's

#### Scenario: Losing the race is explained

- **WHEN** a user acknowledges an alert another user just took
- **THEN** they are told who holds it and the list updates

### Requirement: Alerts surface outside the panel

The navigation SHALL carry an indicator of unacknowledged alerts for the active branch, so an
alert is visible without opening the panel. The indicator SHALL update from the realtime
notification.

#### Scenario: A firing alert is visible immediately

- **WHEN** an alert fires for the active branch while the user is elsewhere in the app
- **THEN** the navigation indicator reflects it without a reload

#### Scenario: The indicator clears

- **WHEN** every alert of the active branch is acknowledged or resolved
- **THEN** the indicator clears

#### Scenario: Polling fallback

- **WHEN** the realtime channel is unavailable
- **THEN** the panel and indicator still update on their polling interval

### Requirement: Rule configuration screen

The front SHALL expose a rule configuration screen, gated on `alerts.manage`, listing every
known rule for the active branch with its enablement, threshold where applicable, recovery
buffer, escalation delay and whether it escalates to WhatsApp. The screen SHALL explain what
the recovery buffer does, since it is what prevents the alert from repeating.

#### Scenario: Enabling a rule

- **WHEN** a user with `alerts.manage` enables a rule and saves
- **THEN** that rule begins firing for the branch

#### Scenario: Recovery buffer is explained

- **WHEN** the configuration screen is shown
- **THEN** the recovery buffer is presented with an explanation of the repetition it prevents

#### Scenario: Zero buffer is refused in the UI

- **WHEN** a user sets a recovery buffer of zero
- **THEN** saving is refused with a clear message

#### Scenario: WhatsApp escalation reflects availability

- **WHEN** the branch has no connected WhatsApp session
- **THEN** the escalation-to-WhatsApp option explains it will not deliver

### Requirement: Permission gating and navigation

The alerts panel SHALL require `alerts.read` and the rule configuration screen
`alerts.manage`; both SHALL be hidden from navigation and refused on direct entry without
them.

#### Scenario: Panel hidden without read

- **WHEN** a user without `alerts.read` is signed in
- **THEN** the alerts entry and its indicator are absent, and direct entry is refused

#### Scenario: Read-only user cannot configure

- **WHEN** a user has `alerts.read` but not `alerts.manage`
- **THEN** they can list and acknowledge alerts, and the configuration screen is unavailable
