## ADDED Requirements

### Requirement: Charging a table is one gesture, not three

The Caja SHALL offer a table settlement panel listing the branch's occupied tables with open orders,
their diner count and their running sum. Opening a table SHALL preselect **all** its open orders,
each shown under its diner name with its label, lines and total.

The default is the common case: almost every table pays together. Splitting is the same panel with
members deselected, not a different screen — a separate "split mode" would duplicate the charge, the
close and the receipt and force a decision about what happens when a table pays half and half.

Deselecting every member SHALL disable the charge rather than charge nothing.

#### Scenario: A table settles together by default
- **WHEN** the cashier opens table 5 with three open orders
- **THEN** all three are selected, grouped by diner, and the panel shows their combined total

#### Scenario: One diner pays alone
- **WHEN** the cashier deselects two of the three
- **THEN** the total shown is the remaining diner's, and charging settles only that order

#### Scenario: The table's growth is reflected
- **WHEN** a diner adds a round while the panel is open and the panel refreshes
- **THEN** the shown total reflects the added item before the charge is taken

#### Scenario: Nothing selected charges nothing
- **WHEN** every member is deselected
- **THEN** the charge action is unavailable

### Requirement: The cashier sees what each payment covered

The panel SHALL accept one or more payments of different methods until the selection is covered,
showing the remaining amount after each. On settlement it SHALL report which orders were closed.

The cash ledger records one movement per member order. The feed SHALL show that those movements
belong to one charge, so a cashier reconciling a shift is not left wondering why one bill produced
three lines.

#### Scenario: Remaining amount is always visible
- **WHEN** a partial payment is registered against the selection
- **THEN** the outstanding amount is shown and the table stays open

#### Scenario: Settlement reports what closed
- **WHEN** the selection is covered
- **THEN** the panel reports the orders that closed and offers the receipt

#### Scenario: One charge reads as one charge in the ledger
- **WHEN** a table charge produces several cash movements
- **THEN** the movement feed presents them as belonging to the same table charge

### Requirement: A diner going on credit leaves the selection

When a member order is to be settled on credit, the panel SHALL direct the cashier to remove it from
the selection and settle it through the existing single-order flow, which assigns a customer and
records the credit.

A bill is charged in full or not at all. The panel SHALL say this plainly rather than failing with a
validation error after the cashier has already taken money.

#### Scenario: Credit is refused inside the selection
- **WHEN** the cashier attempts to leave a member uncovered
- **THEN** the panel explains that the member must be removed and settled on its own

### Requirement: The table receipt prints and declares itself

The Caja SHALL render a printable table receipt carrying the business name, tax id, address and
branch, the table, the date and time, the cashier, every settled order grouped under its diner with
its label and lines, the totals, and the payment methods used. Printing SHALL record the print, and
a second print SHALL be recorded as a reprint.

The receipt SHALL state that it is not an electronic invoice, in words the customer can read.

#### Scenario: Print after settling
- **WHEN** a table settles and the cashier prints
- **THEN** a receipt renders with the business and table data, every diner's lines and the totals

#### Scenario: The receipt does not pretend to be a factura
- **WHEN** the receipt renders
- **THEN** it carries a legible statement that it is not an electronic invoice

#### Scenario: A second print is a reprint
- **WHEN** the cashier prints the same table receipt again
- **THEN** the print is recorded as a reprint
