# frontend-driver

## Purpose

The driver mobile view (`/driver`): a real-data console that lets a courier open their
own despacho, work its stops in route order, act at the doorstep (mark delivered or
not-delivered with a reason), and see their stops on a map — all backed by the real
delivery/driver API with no in-memory mock layer.

## Requirements

### Requirement: The driver view is backed by real delivery data

The driver mobile view (`/driver`) SHALL read and mutate real delivery data through the delivery API, with no in-memory mock data layer. Its store SHALL follow write-through discipline: each mutation calls the API and refetches the driver's own run. The driver identity (name shown in the header) SHALL come from the authenticated user's employee record, not a hardcoded sample.

#### Scenario: The view loads the real active run
- **WHEN** a driver opens `/driver` with an active run on the server
- **THEN** the view shows that run's real stops, ordered by delivery order, with the driver's real name

#### Scenario: No mock fallback
- **WHEN** the driver has no active run
- **THEN** the view shows the empty state driven by the server, not fabricated stops

### Requirement: Open a despacho from the driver view

The driver view SHALL let the driver open a despacho for themselves. Opening SHALL call the driver self-open action and then show the resulting run. When the driver cannot open (no route assigned), the view SHALL surface the reason rather than fail silently.

#### Scenario: Driver opens a despacho
- **WHEN** a driver on the empty state taps "Abrir despacho"
- **THEN** the view opens a run server-side and shows its stops

#### Scenario: Cannot open without a route
- **WHEN** opening is rejected because the driver drives no route
- **THEN** the view shows an explanatory message and stays on the empty state

### Requirement: Next stop derived from route order, not per-stop transit flag

Because departing a run moves all its deliveries to `in_transit` at once, the driver view SHALL derive the highlighted "siguiente pedido" from route position plus terminal status — the first stop not yet delivered or not-delivered — rather than from a single per-stop in-transit flag. Stops already delivered or not-delivered SHALL render in their terminal state.

#### Scenario: Highlight the first unsettled stop
- **WHEN** a run is in transit with some stops already settled
- **THEN** the view highlights the first stop, by route order, that is neither delivered nor not-delivered

### Requirement: Enriched stop detail and doorstep actions

The stop detail SHALL show the order data joined server-side — customer, phone (one-tap call), items, total, and payment method (emphasizing the cash amount to collect) — and SHALL let the driver mark the stop delivered, or not-delivered with a reason chosen from the fixed list plus an optional comment. Marking SHALL call the real API and advance to the next stop.

#### Scenario: Mark delivered
- **WHEN** a driver marks the open stop as delivered
- **THEN** the delivery is marked delivered server-side and the view advances to the next stop

#### Scenario: Mark not-delivered with a reason
- **WHEN** a driver marks the open stop as not delivered and selects a reason (optionally a comment)
- **THEN** the delivery is marked not-delivered with that reason server-side and the view advances

### Requirement: Real destination pins on the driver map

The driver map SHALL render each stop from its real destination coordinates, colored by status, with the next stop emphasized. Stops missing coordinates SHALL be surfaced (not silently dropped). The driver's own live position marker is out of scope for this capability.

#### Scenario: Stops plotted from real coordinates
- **WHEN** the driver opens the map with a run whose stops have coordinates
- **THEN** each stop is plotted at its real location, colored by status, next stop emphasized

#### Scenario: A stop without coordinates is surfaced
- **WHEN** a stop has no destination coordinates
- **THEN** the view indicates it is unlocated rather than omitting it without notice
