# product-costing (delta)

## ADDED Requirements

### Requirement: Ingredient unit cost exposed for menu editing

The system SHALL expose each ingredient's current **unit cost** — the same
moving-average of purchase prices used for product-cost rollup — as a read the menu
editor can consume at edit time, scoped to the tenant. An ingredient with no
purchase history SHALL report its unit cost as unavailable (null), never as zero, so
the editor can distinguish "no cost yet" from "free."

#### Scenario: Unit cost from purchase history

- **WHEN** an authorized user requests ingredient unit costs and an ingredient has
  one or more purchase lines
- **THEN** the response includes that ingredient's unit cost as the moving-average of
  those lines' unit prices, in the ingredient's unit

#### Scenario: Unavailable cost is not zeroed

- **WHEN** an ingredient has no purchase history
- **THEN** its unit cost is reported as unavailable (null)
- **AND** it is not reported as `0`

#### Scenario: Tenant isolation of costs

- **WHEN** a request for tenant A reads ingredient unit costs
- **THEN** only ingredients whose `tenant_id` equals tenant A are returned, with
  costs derived only from tenant A's purchases
