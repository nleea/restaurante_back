## ADDED Requirements

### Requirement: An alert can be silenced from the panel

The alerts panel SHALL offer, on an open unacknowledged alert, an action that stops its reminders
without recording that anybody took it. A silenced alert SHALL still be listed as open and SHALL
show that it is silenced.

#### Scenario: Silencing from the panel

- **WHEN** a user with permission to act on alerts silences one
- **THEN** it stops being reminded and stays visible in the panel

#### Scenario: A silenced alert says so

- **WHEN** a silenced alert is listed
- **THEN** the panel shows that its reminders are off, distinctly from an acknowledged one

#### Scenario: Silencing is not taking

- **WHEN** an alert is silenced
- **THEN** it is not shown as taken by anybody

### Requirement: The panel explains what silencing does

The panel SHALL make clear that silencing stops the reminders for that one alert only, and that a
new alert for the same condition will remind again. Without that, silencing reads as "turn this
rule off" and nobody will use it.

#### Scenario: The scope of silencing is stated

- **WHEN** the silence action is presented
- **THEN** it states that it affects only this alert and only while it stays open

### Requirement: The rule screen configures the reminder interval

The rule configuration screen SHALL let a manager set each rule's reminder interval, SHALL state
that zero means no reminders, and SHALL state the floor imposed by the sweep so a shorter value is
not read as broken.

#### Scenario: Setting an interval

- **WHEN** a manager sets a rule's reminder interval and saves
- **THEN** the value is persisted and shown on the next load

#### Scenario: Zero is presented as an explicit choice

- **WHEN** the interval is zero
- **THEN** the screen says that this rule will notify once and never remind

#### Scenario: The sweep floor is stated

- **WHEN** the interval field is shown
- **THEN** the screen states the shortest cadence reminders can actually arrive at
