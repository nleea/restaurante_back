"""Menu module: categories, products, prices, variants and addons.

Models the sellable catalog of each tenant: hierarchical `categories`,
`products` (with per-branch `product_prices`), configurable `variant_groups`
and `variant_options`, optional `addons`, and the concrete `product_variants`
(SKUs) built from the chosen options.
"""
