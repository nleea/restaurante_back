## ADDED Requirements

### Requirement: Delivery changes publish realtime events

Delivery and run mutations SHALL publish a best-effort `delivery` realtime event scoped to the branch, so live views (dispatch board, coverage map, driver) can refresh. This SHALL include: creating a delivery, assigning it, departing a run, marking a delivery delivered/not-delivered, finishing a run, a driver self-opening a run, and the **geocoding worker resolving a delivery's pin** (a separate process, whose change would otherwise be invisible to open screens). Publishing SHALL be best-effort and SHALL NOT fail the mutation if the broker is down.

#### Scenario: Creating a delivery notifies the branch
- **WHEN** a delivery is created for a branch
- **THEN** a `delivery` event for that branch is published

#### Scenario: A lifecycle transition notifies the branch
- **WHEN** a delivery is assigned, departed, marked, or a run is finished
- **THEN** a `delivery` event for that branch is published

#### Scenario: The geocoding worker's pin resolution notifies the branch
- **WHEN** the background geocoding worker resolves a delivery's location
- **THEN** a `delivery` event for that branch is published, so an open map updates

#### Scenario: A broker outage does not block the mutation
- **WHEN** the broker is unavailable during a delivery mutation
- **THEN** the mutation succeeds and no event is delivered

### Requirement: Delivery events stream

The system SHALL expose the branch's `delivery` events as an SSE stream under `delivery.read`, so a browser can subscribe and refetch on change.

#### Scenario: A dispatcher streams delivery events
- **WHEN** a client holding `delivery.read` opens the delivery events stream for a branch
- **THEN** it receives that branch's delivery events

#### Scenario: Streaming without permission is rejected
- **WHEN** a client lacking `delivery.read` opens the delivery events stream
- **THEN** the request is rejected
