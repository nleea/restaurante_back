## ADDED Requirements

### Requirement: Permission is asked on an explicit gesture, never on load

The system SHALL request notification permission only in response to the user turning notifications
on, and SHALL NOT request it while a page is merely loading. A browser refusal is permanent from
the page's side, so an unprompted request spends the only chance there is.

#### Scenario: Loading does not ask

- **WHEN** the app loads with notifications never configured
- **THEN** no permission prompt is raised

#### Scenario: Turning them on asks

- **WHEN** the user turns notifications on
- **THEN** permission is requested

#### Scenario: A denial is reported, not retried

- **WHEN** the user denied permission in the browser
- **THEN** the app states that the browser is blocking them and does not ask again

### Requirement: A new alert raises a system notification

While notifications are enabled and permitted, a newly fired alert SHALL raise one operating-system
notification naming the subject, and SHALL do so even when the tab is in the background.

#### Scenario: A new alert notifies

- **WHEN** an alert fires while the app is open in a background tab
- **THEN** one system notification is raised naming that alert's subject

#### Scenario: Disabled means silent

- **WHEN** notifications are turned off
- **THEN** no system notification is raised for a new alert

#### Scenario: Activating the notification opens the alert

- **WHEN** the user activates a notification
- **THEN** the app is focused showing that alert in the panel

### Requirement: Reminders do not raise repeated system notifications

A reminder for an alert already notified SHALL NOT raise another system notification. Repetition
belongs to the in-app panel; repeating it on the desktop is what makes people switch notifications
off for good.

#### Scenario: A reminded alert does not re-notify the desktop

- **WHEN** an already-notified alert is reminded
- **THEN** no further system notification is raised for it

#### Scenario: A different alert still notifies

- **WHEN** a second, different alert fires
- **THEN** it raises its own system notification

### Requirement: The tab title carries the open count

The document title SHALL carry the number of open alerts for the active branch, and SHALL restore
the plain title when there are none. This SHALL work regardless of notification permission, since
it is the only signal that never needs one.

#### Scenario: Open alerts show in the title

- **WHEN** there are open alerts
- **THEN** the tab title carries their count

#### Scenario: The title clears

- **WHEN** the last open alert is dealt with
- **THEN** the title returns to its plain form

#### Scenario: The count works without permission

- **WHEN** notification permission is denied
- **THEN** the tab title still carries the count

### Requirement: Sound is opt-in and per device

An audible cue MAY accompany a new alert, SHALL be off unless turned on, and SHALL be stored per
device rather than per user account.

#### Scenario: Sound is off by default

- **WHEN** notifications are enabled without touching sound
- **THEN** a new alert makes no sound

#### Scenario: The preference does not follow the user to another device

- **WHEN** a user enables sound on one device and signs in on another
- **THEN** the second device has sound off

### Requirement: Unsupported browsers degrade without breaking

Where the browser exposes no notification support, the app SHALL keep working, SHALL keep the tab
title count, and SHALL say that this browser cannot show notifications.

#### Scenario: No support, no crash

- **WHEN** the browser exposes no notification API
- **THEN** the panel works, the title count works, and the app says notifications are unavailable
