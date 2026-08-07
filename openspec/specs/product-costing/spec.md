# product-costing

## Purpose

Derives cost of goods from existing purchasing and recipe data: ingredient unit
cost from purchase history, product cost by rolling up the recipe BOM, and period
COGS for sold order items. Provides the cost side that lets finance reporting
compute gross margin, and surfaces partial/unavailable costs honestly rather than
defaulting them to zero.

## Requirements

### Requirement: Ingredient unit cost from purchasing

The system SHALL derive an ingredient's unit cost from purchasing history — the moving-average (or latest) `purchase_order_lines.unit_price` for that ingredient, normalized to the ingredient's stock unit. When an ingredient has no purchase history, its cost SHALL be reported as unavailable rather than zero.

#### Scenario: Cost from purchase history

- **WHEN** an ingredient has one or more purchase lines
- **THEN** its unit cost is the moving-average of those lines' unit prices in the ingredient's unit

#### Scenario: No purchase history

- **WHEN** an ingredient has never been purchased
- **THEN** its cost is reported as unavailable, not zero

### Requirement: Ingredient unit cost exposed for menu editing

The system SHALL expose each ingredient's current **unit cost** — the same moving-average of purchase prices used for product-cost rollup — as a read the menu editor can consume at edit time, scoped to the tenant. An ingredient with no purchase history SHALL report its unit cost as unavailable (null), never as zero, so the editor can distinguish "no cost yet" from "free".

#### Scenario: Unit cost from purchase history

- **WHEN** an authorized user requests ingredient unit costs and an ingredient has one or more purchase lines
- **THEN** the response includes that ingredient's unit cost as the moving-average of those lines' unit prices, in the ingredient's unit

#### Scenario: Unavailable cost is not zeroed

- **WHEN** an ingredient has no purchase history
- **THEN** its unit cost is reported as unavailable (null)
- **AND** it is not reported as `0`

#### Scenario: Tenant isolation of costs

- **WHEN** a request for tenant A reads ingredient unit costs
- **THEN** only ingredients whose `tenant_id` equals tenant A are returned, with costs derived only from tenant A's purchases

### Requirement: Product cost from the recipe BOM

The system SHALL compute a product's cost by rolling up its recipe items — for each `recipe_item`, ingredient quantity × ingredient unit cost — and summing. A product with any unavailable-cost ingredient SHALL surface that its cost is partial/estimated.

#### Scenario: Roll up BOM to product cost

- **WHEN** a product has a recipe with priced ingredients
- **THEN** its cost equals the sum over recipe items of (quantity × ingredient unit cost)

#### Scenario: Partial cost flagged

- **WHEN** a product's recipe contains an ingredient with unavailable cost
- **THEN** the product cost is flagged as partial/estimated

### Requirement: COGS for sold items

The system SHALL expose COGS for a period as the sum over sold `order_items` of (product cost × quantity), so profitability reporting can compute gross margin.

#### Scenario: Period COGS

- **WHEN** COGS is requested for a branch and date range
- **THEN** it equals the sum over that period's sold items of product cost × quantity

#### Scenario: Margin becomes computable

- **WHEN** both revenue and COGS are available for a period
- **THEN** gross margin (revenue − COGS) and margin % can be derived per channel and overall
