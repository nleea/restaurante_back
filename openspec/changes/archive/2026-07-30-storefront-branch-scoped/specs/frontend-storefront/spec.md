## ADDED Requirements

### Requirement: Storefront route carries a branch code

The public storefront route SHALL accept an optional branch code segment
(`/store/:branchCode?`). When a code is present, the view SHALL load that branch's menu,
prices and hours and submit the order to that branch. When it is absent, the view SHALL
behave as today, using the tenant's primary branch.

#### Scenario: Branch link opens that branch's carta

- **WHEN** a customer opens `/store/centro`
- **THEN** the storefront shows the `centro` branch's menu, prices and open/closed state

#### Scenario: Code-less link keeps working

- **WHEN** a customer opens `/store`
- **THEN** the storefront shows the primary branch's menu exactly as before

#### Scenario: Checkout posts to the addressed branch

- **WHEN** a customer checks out from `/store/centro`
- **THEN** the order is submitted to that branch's intake endpoint

### Requirement: Unknown branch code shows a not-found state

When the addressed branch code does not resolve to an active branch, the storefront SHALL
show a clear not-found state offering the branch picker. It SHALL NOT silently load another
branch's menu.

#### Scenario: Wrong code is visible, not silent

- **WHEN** a customer opens `/store/no-existe`
- **THEN** the storefront shows a not-found state and no menu of any other branch

### Requirement: Branch picker when no branch is addressed

The storefront SHALL offer a branch picker when no branch code is present in the route and
the tenant has more than one active branch, listing those branches by name and address and
navigating to `/store/:branchCode` on selection. With a single active branch, no picker is
shown.

#### Scenario: Multi-branch tenant offers a choice

- **WHEN** a customer opens `/store` on a tenant with three active branches
- **THEN** a picker lists the branches and selecting one navigates to that branch's carta

#### Scenario: Single-branch tenant shows no picker

- **WHEN** a customer opens `/store` on a tenant with one active branch
- **THEN** the carta is shown directly with no picker

### Requirement: Cart is cleared when the branch changes

Prices, availability and variants belong to a branch, so the cart SHALL NOT be carried
across branches. When the customer moves to a different branch code with a non-empty cart,
the storefront SHALL clear the cart and tell the customer it did.

#### Scenario: Switching branch empties the cart

- **WHEN** a customer with items in the cart navigates from `/store/centro` to
  `/store/norte`
- **THEN** the cart is emptied and the customer is told the carta changed

#### Scenario: Reloading the same branch keeps the cart

- **WHEN** a customer reloads `/store/centro` with items in the cart
- **THEN** the cart is preserved
