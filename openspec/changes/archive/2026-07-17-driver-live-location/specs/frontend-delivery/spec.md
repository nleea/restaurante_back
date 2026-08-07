## ADDED Requirements

### Requirement: Live driver layer on the coverage map

The coverage map SHALL render a live driver layer so the dispatcher can see the domiciliario: for each active run, the driver's current-position marker (distinct from delivery drops and the branch pin, labeled with the driver's name) and their recorded trail as a polyline. Each driver marker SHALL show how fresh its position is (e.g. "hace X min"); positions older than a staleness threshold SHALL be visually de-emphasized rather than shown as if live. The layer SHALL refresh on an interval (or via realtime push) and SHALL show only active runs.

#### Scenario: Active driver appears on the coverage map
- **WHEN** a driver is tracking during an active run and the dispatcher views the coverage map
- **THEN** the map shows that driver's current-position marker and trail, labeled with the driver's name

#### Scenario: Staleness is shown
- **WHEN** a driver's latest position is several minutes old
- **THEN** the marker shows its age and is de-emphasized rather than presented as current

#### Scenario: Finished runs leave the layer
- **WHEN** a run finishes
- **THEN** its driver marker and trail are removed from the live layer on the next refresh

#### Scenario: The layer refreshes
- **WHEN** a tracked driver moves and time passes
- **THEN** the dispatcher's map updates the driver's marker and extends the trail without a manual reload
