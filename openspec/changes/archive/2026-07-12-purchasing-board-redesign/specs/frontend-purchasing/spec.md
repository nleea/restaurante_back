# frontend-purchasing (delta)

## MODIFIED Requirements

### Requirement: Permission gating and navigation

The Purchasing surface SHALL be hosted inside the unified Compras board at `/purchasing` as its
**Proveedores** area tab (not a standalone screen), reachable only for authenticated users with
`purchasing.read` via the single Compras navigation entry; the supplier create/edit/deactivate and
the catalog attach/detach controls SHALL be shown only with `purchasing.manage`. This gating is
UX — the backend enforces authorization independently.

#### Scenario: Suppliers live in the Proveedores tab

- **WHEN** an authenticated user with `purchasing.read` opens the Proveedores area tab of the Compras
  board
- **THEN** the supplier list, contact info, and ingredient catalog are shown, with create/edit/
  deactivate/attach/detach controls gated by `purchasing.manage`

#### Scenario: Read-only purchasing user

- **WHEN** the current user has `purchasing.read` but not `purchasing.manage`
- **THEN** the supplier list, contact info, and catalog are visible read-only and no create, edit,
  deactivate, attach, or detach actions are shown

#### Scenario: Route guarded by permission

- **WHEN** a user without `purchasing.read` navigates to `/purchasing`
- **THEN** the router redirects them to the forbidden view
