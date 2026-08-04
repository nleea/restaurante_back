## ADDED Requirements

### Requirement: The panel turns browser notifications on

The alerts panel SHALL offer a control to enable browser notifications and their optional sound,
SHALL show the current permission state in plain words, and SHALL explain that the browser must
stay open for them to arrive.

#### Scenario: Enabling from the panel

- **WHEN** a user enables notifications from the panel
- **THEN** permission is requested and the panel reflects the outcome

#### Scenario: A blocked permission is explained

- **WHEN** the browser has blocked notifications
- **THEN** the panel says so and says it must be re-enabled in the browser, not in the app

#### Scenario: The limitation is stated up front

- **WHEN** the notification control is shown
- **THEN** the panel states that notifications need a tab of the app to stay open

### Requirement: The panel feeds new alerts to the notifier

The panel SHALL raise a notification for alerts that are new since the last refresh, and SHALL NOT
re-notify alerts already seen in this session.

#### Scenario: Only genuinely new alerts notify

- **WHEN** a refresh returns one alert already listed and one new one
- **THEN** only the new one raises a notification

#### Scenario: A reload does not replay old alerts

- **WHEN** the panel loads and finds alerts that were already open
- **THEN** no notification is raised for them
