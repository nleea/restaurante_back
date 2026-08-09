## MODIFIED Requirements

### Requirement: Ticket editing uses real menu variants and server totals

Order editing SHALL happen in the routed Comanda, and items SHALL NOT reach the kitchen on
add. When adding a product the user MAY attach a free-text **kitchen note** ("sin
lechuga"); the note is shown on the dupe line and travels to the KDS. Each line SHALL show
its kitchen state — **PENDIENTE** (not yet sent) or **EN COCINA** (`sent`) — and an
**Enviar a cocina** action SHALL route the pending lines (repeatable per round). Adding
items and sending are distinct steps.

Adding a product SHALL send the variant and the quantity only. The app SHALL NOT compute, hold or
transmit a line price, and SHALL NOT build an index of the menu in order to name or price a line: a
line's label and price come from the line itself.

That is the load-bearing part of this requirement, so it is worth stating why. Building that index cost
one request per product before the screen was usable, and it made the browser responsible for money —
a stale index charged a stale price, and an empty one charged zero.

#### Scenario: Add an item with a note, still pending

- **WHEN** the user taps a product and adds a kitchen note
- **THEN** the line appears with the note and a PENDIENTE state, and no ticket is created yet

#### Scenario: Adding a product sends no price

- **WHEN** the user taps a product to add it
- **THEN** the request carries the variant and the quantity, and no price

#### Scenario: A line reads without the menu

- **WHEN** the Comanda renders its lines
- **THEN** each line shows its product name, its variant name and its price from the line data alone,
  having read no menu endpoint

#### Scenario: Send to the kitchen

- **WHEN** the user presses "Enviar a cocina" with pending lines
- **THEN** those lines are routed and flip to EN COCINA

#### Scenario: Send a later round

- **WHEN** more items are added after a first send and the user sends again
- **THEN** only the new pending lines are routed

### Requirement: Live floor grid backed by real tables and orders

The Salón SHALL render one card per dining table of the active branch, built from real tables and real
open orders, and SHALL show occupancy counts over the branch's tables. Cards SHALL refresh while the
screen is mounted, from the realtime `orders` stream when it is healthy and by polling as a fallback.

The grid SHALL include the kitchen readiness rollup on its cards. It SHALL NOT be disabled to make the
screen load faster: the rollup is what turns a card from "occupied" into "this table is waiting on
food", and a Salón without it is a seating chart.

Loading the floor SHALL NOT require reading the menu. Tables, open orders and their lines SHALL be
obtained without a request per order and without a request per product.

#### Scenario: Cards show readiness, not just occupancy

- **WHEN** the Salón loads with open orders that have kitchen tickets
- **THEN** the cards show the readiness rollup, not only occupied/total

#### Scenario: The floor loads without the menu

- **WHEN** the Salón loads
- **THEN** no menu endpoint is requested, and no request is made per open order

#### Scenario: A kitchen hiccup still degrades gracefully

- **WHEN** the kitchen data cannot be read
- **THEN** the cards fall back to plain occupancy and the Salón still works
