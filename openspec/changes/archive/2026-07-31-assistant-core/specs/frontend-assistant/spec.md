## ADDED Requirements

### Requirement: Admin chat panel

The front SHALL expose a chat panel where a signed-in employee can ask questions in natural
language and receive answers produced within their own permissions. The panel SHALL make clear
which branch the conversation is about, and SHALL indicate that the assistant cannot make
changes.

#### Scenario: An employee asks a question

- **WHEN** an entitled tenant's employee asks a question in the panel
- **THEN** an answer is returned, derived from data their permissions allow

#### Scenario: The answer respects the asker's permissions

- **WHEN** an employee without the finance permission asks about sales figures
- **THEN** they do not receive that data

#### Scenario: The branch in scope is visible

- **WHEN** the panel is open
- **THEN** it shows which branch the questions are about

#### Scenario: Read-only is stated

- **WHEN** the panel is open
- **THEN** it makes clear the assistant answers but does not change anything

### Requirement: Panel is hidden without entitlement

The chat panel SHALL be unavailable when the tenant is not entitled to the assistant, and the
front SHALL explain that it is not enabled rather than presenting a broken chat.

#### Scenario: Unentitled tenant sees no chat

- **WHEN** a tenant without the assistant is signed in
- **THEN** the chat panel is absent from navigation and direct entry explains it is not enabled

### Requirement: Usage and quota screen

The front SHALL expose a usage screen, gated on the assistant management permission, showing
consumption against the quota for the current period, the warning threshold, and a breakdown
of recent usage.

#### Scenario: Consumption is visible

- **WHEN** a permitted user opens the usage screen
- **THEN** consumption for the current period is shown against the quota

#### Scenario: The warning threshold is shown

- **WHEN** the usage screen is shown
- **THEN** the threshold at which the owner is warned is visible

#### Scenario: Approaching the limit is obvious

- **WHEN** consumption is past the warning threshold
- **THEN** the screen makes that state visually unmistakable

#### Scenario: Exhausted state explains the fallback

- **WHEN** the quota is exhausted
- **THEN** the screen states that customers now receive the fallback message with the store
  link, and that conversations can still be answered by a person

### Requirement: Limits are distinguishable to the user

When a request is refused, the front SHALL distinguish a rate-limit refusal from an exhausted
quota, since the first resolves in a minute and the second requires buying more.

#### Scenario: Rate limit is explained as temporary

- **WHEN** a request is refused by the per-minute rate limit
- **THEN** the user is told to retry shortly

#### Scenario: Exhausted quota is explained as exhausted

- **WHEN** a request is refused because the quota is spent
- **THEN** the user is told the period's allowance is used up, not to retry

### Requirement: Permission gating and navigation

The chat panel SHALL require a signed-in employee and an entitled tenant; the usage screen
SHALL require the assistant management permission. Both SHALL be hidden from navigation and
refused on direct entry when unavailable.

#### Scenario: Usage screen hidden without permission

- **WHEN** a user without the assistant management permission is signed in
- **THEN** the usage entry is absent from navigation and direct entry is refused
