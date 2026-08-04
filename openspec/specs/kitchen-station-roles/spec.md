# kitchen-station-roles

## Purpose

Let a product↔station mapping carry an optional short `role` label describing what a station does
for that product. The role is frozen onto each ticket at routing time and surfaced on the KDS chit
so each station reads its responsibility without decoding the product name. Tenant/branch-isolated
and RBAC-protected (gated by `kitchen.update` for setup).

## Requirements

### Requirement: A role per product-station mapping

The system SHALL let a product↔station mapping carry an optional `role` — a short free-text label
(≤60 chars) describing what that station does for that product (e.g. "Carne y armado", "Vegetales").
The role SHALL be optional; an empty role preserves today's behavior. A user with `kitchen.update`
SHALL be able to set or clear the role when mapping a product to a station in kitchen setup.

#### Scenario: Map a product to a station with a role

- **WHEN** a user with `kitchen.update` maps a product to a station and enters a role
- **THEN** the mapping is stored with that role and the role appears in the setup list for that mapping

#### Scenario: Role is optional

- **WHEN** a product is mapped to a station with no role
- **THEN** the mapping is stored with an empty role and no role text is shown for it

### Requirement: Routing captures the role onto each ticket

When an order is routed, each created ticket SHALL capture the role from the product↔station mapping
that produced it, so the instruction is fixed at fire time and is not affected by later edits to the
mapping. Re-routing (idempotent) SHALL NOT change the role of a ticket that already exists.

#### Scenario: A multi-station product carries a distinct role per ticket

- **WHEN** a product mapped to two stations with different roles is routed
- **THEN** two tickets are created, each carrying the role of its own station's mapping

#### Scenario: Role is frozen at routing time

- **WHEN** a mapping's role is changed after a ticket for it already exists
- **THEN** the existing ticket keeps the role it was created with

### Requirement: The KDS chit shows the station's role

The kitchen board SHALL display the ticket's `role` beneath the item label when present, so each
station reads what it is responsible for without decoding the product name. When the role is empty,
no role line SHALL be shown.

#### Scenario: Station sees its part

- **WHEN** a station's board renders a ticket that has a role
- **THEN** the chit shows the item label and, beneath it, the role text

#### Scenario: No role, no clutter

- **WHEN** a ticket has no role
- **THEN** the chit shows only the item label, with no empty role line
