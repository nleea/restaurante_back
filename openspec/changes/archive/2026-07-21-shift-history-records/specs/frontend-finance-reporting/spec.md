## ADDED Requirements

### Requirement: Registros por turno view

The Finanzas area SHALL provide a "Registros por turno" view that lists closed sessions and drills into a selected session's operational record (orders/deliveries/tickets/payments), reusing the Reporte Z per-session framing.

#### Scenario: Browse and open a session record

- **WHEN** the user opens "Registros por turno" and selects a closed session
- **THEN** the session's operational record is shown alongside its Reporte Z

#### Scenario: Empty history

- **WHEN** a branch has no closed sessions yet
- **THEN** the view shows an empty state rather than an error
