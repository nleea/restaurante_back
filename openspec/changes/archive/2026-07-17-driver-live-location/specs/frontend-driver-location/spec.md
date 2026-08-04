## ADDED Requirements

### Requirement: Consented, active-run-only location tracking

The driver app SHALL capture the driver's browser location only while a run is active and only after the driver has granted permission and enabled tracking via an explicit on/off control. Tracking SHALL stop when the run finishes, when the driver turns it off, or when no run is active. If permission is denied, the driver SHALL still be able to work the run; the app SHALL NOT block on location.

#### Scenario: Tracking starts on consent during an active run
- **WHEN** a driver with an active run enables tracking and grants the browser permission
- **THEN** the app begins capturing the driver's position

#### Scenario: Tracking stops when the run finishes
- **WHEN** the active run is finished or the driver turns tracking off
- **THEN** the app stops capturing position

#### Scenario: Denied permission is non-blocking
- **WHEN** the driver denies the browser location permission
- **THEN** the driver can still open, work, and finish the run without location

### Requirement: Throttled position sampling

While tracking, the app SHALL send position samples throttled by both time and distance (not on every raw update), to respect battery and the API, and SHALL push each sample to the driver's own-run location endpoint.

#### Scenario: Samples are throttled
- **WHEN** the device emits frequent position updates
- **THEN** the app sends a sample only after enough time and distance have passed since the last sent point

#### Scenario: A sample is pushed to the own run
- **WHEN** a throttled sample is ready and a run is active
- **THEN** the app pushes it to the driver's own-run location endpoint

### Requirement: The driver sees their own live position and trail

The driver map SHALL show the driver's own current position from live geolocation (replacing any fixed placeholder), alongside their stops, so the driver can see where they are relative to the next stop. It SHALL also draw the driver's own accumulated **trail** for the active run, built from the local fixes it already has (no server round-trip needed for the driver's own view).

#### Scenario: Own position replaces the placeholder
- **WHEN** tracking is active and a fix is available
- **THEN** the driver map shows the driver's real current position, not a fixed constant

#### Scenario: The driver's own trail is drawn
- **WHEN** the driver has moved and several fixes have been captured during the run
- **THEN** the driver map draws the path they have travelled, plus the current position

#### Scenario: No fix yet
- **WHEN** tracking is enabled but no fix is available yet
- **THEN** the map shows the stops without a misleading own-position marker
