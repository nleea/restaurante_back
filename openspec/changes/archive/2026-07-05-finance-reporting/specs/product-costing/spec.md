## ADDED Requirements

### Requirement: Ingredient unit cost from purchasing

The system SHALL derive an ingredient's unit cost from purchasing history — the moving-average (or latest) `purchase_order_lines.unit_price` for that ingredient, normalized to the ingredient's stock unit. When an ingredient has no purchase history, its cost SHALL be reported as unavailable rather than zero.

#### Scenario: Cost from purchase history

- **WHEN** an ingredient has one or more purchase lines
- **THEN** its unit cost is the moving-average of those lines' unit prices in the ingredient's unit

#### Scenario: No purchase history

- **WHEN** an ingredient has never been purchased
- **THEN** its cost is reported as unavailable, not zero

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
