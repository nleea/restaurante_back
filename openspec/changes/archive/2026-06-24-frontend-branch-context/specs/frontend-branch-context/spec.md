## ADDED Requirements

### Requirement: Active-branch context store

The frontend SHALL provide a shared branch-context store that loads the available branches from `GET /branches`, exposes the list and the currently `activeBranchId`, and lets any screen read the active branch without knowing how it was resolved. Loading SHALL be idempotent: once loaded, repeated calls SHALL NOT refetch. The store SHALL expose `hasActiveBranch` and an `ensureLoaded()` action that resolves after the branches are available.

#### Scenario: Branches load on first use

- **WHEN** `ensureLoaded()` is called for the first time
- **THEN** the store fetches `GET /branches`, populates the branch list, and resolves the active branch

#### Scenario: Load is idempotent

- **WHEN** `ensureLoaded()` is called again after a successful load
- **THEN** the store does not issue another `GET /branches` request and keeps the current selection

### Requirement: Default branch selection

When no branch has been previously chosen, the store SHALL default the active branch to the tenant's primary branch (`is_primary = true`); if none is marked primary, it SHALL default to the first branch returned. If the tenant has no branches, `hasActiveBranch` SHALL be `false` and `activeBranchId` SHALL be `null`.

#### Scenario: Primary branch is preferred

- **WHEN** the branch list contains a branch with `is_primary = true` and no prior selection exists
- **THEN** that branch becomes the `activeBranchId`

#### Scenario: Falls back to the first branch

- **WHEN** the branch list has no branch marked `is_primary` and no prior selection exists
- **THEN** the first returned branch becomes the `activeBranchId`

#### Scenario: No branches available

- **WHEN** `GET /branches` returns an empty list
- **THEN** `hasActiveBranch` is `false` and `activeBranchId` is `null`

### Requirement: Persisted branch selection

The store SHALL expose `setActiveBranch(id)` to switch the active branch and SHALL persist the selection in `localStorage`. On a later load, if the persisted id still matches an available branch, the store SHALL restore it instead of applying the default; if it no longer matches, the store SHALL fall back to the default selection.

#### Scenario: Selection survives reload

- **WHEN** the user selects a branch via `setActiveBranch(id)` and later reloads the app
- **THEN** `ensureLoaded()` restores that same branch as `activeBranchId`

#### Scenario: Stale persisted selection is discarded

- **WHEN** a persisted branch id no longer appears in the `GET /branches` response
- **THEN** the store ignores the persisted id and applies the default selection rule

### Requirement: Branch selector in the app shell

The authenticated app shell SHALL render a branch selector showing the active branch's name, reachable on both the desktop sidebar and the mobile top bar. When the tenant has more than one branch, the selector SHALL let the user switch via `setActiveBranch(id)`; when the tenant has a single branch, it SHALL render the branch name as a static, non-interactive label.

#### Scenario: Switching branches with multiple branches

- **WHEN** the tenant has multiple branches and the user picks a different one in the selector
- **THEN** the store's `activeBranchId` updates and screens reading it reflect the new branch

#### Scenario: Single-branch tenant shows a static label

- **WHEN** the tenant has exactly one branch
- **THEN** the selector displays that branch's name without an interactive switch control
