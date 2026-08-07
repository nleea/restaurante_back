## ADDED Requirements

### Requirement: A table card shows how many are eating and what they owe

The Salón's table card SHALL show, for an occupied table, how many orders are open on it and their
combined total, and SHALL name the diners when the orders carry names.

A table that serves itself is no longer entered from this screen — it is watched from it. The card
stops being an input control and becomes the answer to the only two questions anyone asks while
crossing the room: how many are on that table, and how much is on it.

#### Scenario: An occupied table states its load
- **WHEN** a table holds three open orders
- **THEN** its card shows three diners, their names, and the combined total

#### Scenario: A table with one order reads as before
- **WHEN** a table holds a single open order
- **THEN** the card shows it as it does today, with the diner named when there is one

#### Scenario: A free table shows nothing to owe
- **WHEN** a table has no open orders
- **THEN** it renders as free with no total

### Requirement: The floor hands a table over to the till

The table card SHALL offer going to that table's settlement in the Caja, carrying the table with it,
for a user who holds the permission to charge orders.

Without waiters, the person who notices that table 5 is done is not necessarily the person at the
till. The path from noticing to charging should be one action, not a re-search by table number.

#### Scenario: Go to settle from the floor
- **WHEN** an authorized user chooses to settle an occupied table from its card
- **THEN** the Caja opens on that table's settlement with its open orders preselected

#### Scenario: Hidden without the permission
- **WHEN** a user without the permission to charge orders views the floor
- **THEN** the settle action is absent
