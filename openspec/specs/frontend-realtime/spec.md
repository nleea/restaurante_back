# frontend-realtime

## Purpose

The frontend side of the realtime foundation: a reusable way for a view to opt
into live updates by subscribing to its topic's stream, treating each event as a
doorbell that triggers a debounced refetch of authoritative data, backed by an
always-on polling fallback so the view stays correct even without a stream.
Subscriptions start when a view is active and tear down cleanly when it is left.
The Delivery and Salón views consume this so changes made elsewhere appear
without a manual refresh.

## Requirements

### Requirement: Live updates via doorbell refetch with a polling fallback

A view that opts into live updates SHALL subscribe to its topic's stream and treat each event as a **doorbell** that triggers a **refetch** of the authoritative data (not application of the event's payload). Bursts of events SHALL be debounced into a single refetch. A **polling fallback** SHALL always run: relaxed while the stream is connected, and at full cadence when the stream is disconnected, so the view stays correct even with no stream. Subscription SHALL start when the view is active and stop when it is left, without leaking timers or connections.

#### Scenario: An event refreshes the view
- **WHEN** a subscribed view receives a stream event
- **THEN** it refetches and shows the updated data without a manual reload

#### Scenario: Bursts collapse into one refetch
- **WHEN** several events arrive within the debounce window
- **THEN** the view refetches once, not once per event

#### Scenario: Polling covers a dropped stream
- **WHEN** the stream disconnects
- **THEN** polling returns to full cadence and the view keeps updating until the stream reconnects

#### Scenario: Leaving the view tears down cleanly
- **WHEN** the user leaves a subscribed view
- **THEN** its stream connection and polling timer are stopped

### Requirement: Delivery and Salón views update live

The dispatch board, the delivery coverage map, the driver view, and the salón/floor SHALL subscribe to their respective streams so a change made elsewhere appears without a manual refresh — e.g. a delivery added from one screen shows on the dispatch board and coverage map, and an order or table change shows on the floor.

#### Scenario: A new delivery appears on the board and map
- **WHEN** a delivery is created (from another screen or the geocoding worker resolving its pin)
- **THEN** the open dispatch board and coverage map show it shortly after, without a manual refresh

#### Scenario: An order/table change appears on the floor
- **WHEN** an order or table changes
- **THEN** the open salón view reflects it shortly after, without a manual refresh
