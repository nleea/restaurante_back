# frontend-inventory (delta)

## ADDED Requirements

### Requirement: Inventory board layout

The Inventory screen SHALL be a board with two areas switched by pill tabs — **Insumos** (the
stock table/cards) and **Alertas** (with a live count badge) — and a slide-in detail drawer for
the selected insumo with Detalles, Movimientos and Alertas tabs. Esc and a close control SHALL
dismiss the drawer; on mobile the drawer takes the full width.

#### Scenario: Open and close the drawer

- **WHEN** the user clicks an insumo row or card
- **THEN** the drawer opens on its detail, and Esc or the close control returns to the list

#### Scenario: Alerts tab badge

- **WHEN** N insumos are low or out of stock
- **THEN** the Alertas tab shows N in its badge

### Requirement: Inventory stats and filters

The board SHALL show live counts (total, en stock, stock bajo, agotados — with percentages)
computed from the loaded branch stock, and SHALL filter the list by category, stock state and a
search string (name or category); active filters SHALL render as dismissable chips with a
clear-all control, and filters combine (AND) and apply live.

#### Scenario: Filters combine

- **WHEN** the user picks a category, the "stock bajo" state and types a name fragment
- **THEN** the list shows only insumos matching all three and chips for each active filter

#### Scenario: Stats reflect loaded data

- **WHEN** a movement changes an insumo's stock state
- **THEN** the stat counts update without a page reload

### Requirement: Depletion bar

Every stock figure SHALL render a depletion bar — a thin bar whose fill maps the on-hand
quantity (in table rows, cards, and the drawer's "stock actual vs mínimo" indicator), with the
reorder threshold marked by a notch at the midpoint, colored by state (success / warn / alert).

#### Scenario: Bar reflects state

- **WHEN** an insumo's on-hand is at or below its threshold but not zero
- **THEN** its depletion bar renders in the warn color with the fill left of the notch

### Requirement: Manage insumos from the board

The board SHALL let an authorized user create an insumo through a two-step modal — nombre,
categoría (suggesting existing categories) and unidad first; stock inicial and mínimo second —
composing the real writes in order (create ingredient, optional initial `in` movement, optional
threshold); a failure after the first write SHALL surface partial-success copy naming what
remains. Editing an insumo's nombre/categoría/unidad SHALL reuse the same modal. Creating and
editing SHALL require the `recipes.manage` permission; the stock-related steps additionally
require `inventory.adjust`.

#### Scenario: Create an insumo with initial stock

- **WHEN** a user with `recipes.manage` and `inventory.adjust` completes both steps with an
  initial stock and a minimum
- **THEN** the insumo appears in the list with that stock, threshold and category, and its
  drawer shows the initial movement

#### Scenario: Partial success is named

- **WHEN** the ingredient is created but the initial movement fails
- **THEN** the modal reports that the insumo exists and the stock inicial is pending, and the
  drawer opens on the created insumo

### Requirement: Inventory alerts area

The Alertas area SHALL list Agotados and Stock bajo sections — each row showing the insumo, its
stock vs minimum (with the depletion bar on low rows) and a CTA that opens the stock modal
pre-set to an `in` movement.

#### Scenario: Restock from an alert

- **WHEN** the user clicks the CTA on an agotado row
- **THEN** the stock modal opens for that insumo pre-set to Entrada

### Requirement: Selection and CSV export

The table SHALL support selecting rows (individually and select-all over the filtered list) with
a floating bulk bar, and the board SHALL export the filtered list — or the selection — as a CSV
file generated client-side.

#### Scenario: Export the filtered list

- **WHEN** the user clicks Exportar with filters active
- **THEN** a CSV containing exactly the filtered rows downloads

## MODIFIED Requirements

### Requirement: Stock list with low-stock view

The InventoryView SHALL list the active branch's tracked insumos showing each one's on-hand
quantity, unit, category, reorder threshold state and last-modified time, in a sortable table
(nombre, stock, última modificación) with a card-view toggle; rows at or below their threshold
SHALL be visibly flagged (warn state and row tint), zero-stock rows flagged as agotado (alert
state and tint), and the stock-state filter SHALL narrow the list to en stock, stock bajo or
agotado.

#### Scenario: Low-stock rows are flagged

- **WHEN** an ingredient's on-hand quantity is at or below its reorder threshold
- **THEN** its row is visibly flagged as low stock

#### Scenario: Filter to only low stock

- **WHEN** the user enables the low-stock filter
- **THEN** only rows at or below their threshold are shown

#### Scenario: Sort by stock

- **WHEN** the user sorts by stock ascending
- **THEN** the emptiest insumos appear first
