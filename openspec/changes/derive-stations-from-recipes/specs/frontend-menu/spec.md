## ADDED Requirements

### Requirement: The carta's stations panel edits what each station owes the dish

The stations panel in the product editor SHALL let an authorized user edit, per assigned station,
the itemized **tasks** that station owes the dish — the sub-lines the cook reads on the pass —
alongside the role it already edits. Tasks SHALL be written as a comma-separated list, since the
panel is narrow and a chip list crowds it, and blank entries between commas SHALL be discarded.

This closes the gap that made the panel unusable in practice: the activation gate sends the person
here, they assign a station, and until now there was nowhere to say what that station actually
does — the task list was only editable from a separate kitchen configuration screen.

#### Scenario: Write a station's tasks

- **WHEN** a user with `kitchen.update` types "Carne, Fundir queso" in a station's tasks field
- **THEN** the mapping is updated with those two tasks, and newly routed orders carry them

#### Scenario: Blank entries are discarded

- **WHEN** the tasks field contains empty segments, e.g. "Carne, , ,Queso,"
- **THEN** only the non-empty names are saved

#### Scenario: Read-only without the kitchen permission

- **WHEN** a user without `kitchen.update` views the panel
- **THEN** the saved tasks are shown as text and no tasks field is offered

### Requirement: Derive a dish's stations and tasks from its recipe

The stations panel SHALL offer a **"Sugerir desde la receta"** action that fetches the product's
station suggestion and presents it as an editable draft: the implied stations preselected, each
with its task list prefilled from the names of the insumos worked at that station.

The action SHALL NOT write anything by itself. The draft is saved only when the person confirms,
through the same attach and update calls the panel already uses, and the prefilled values SHALL
remain editable beforehand so a cook can rename a task or add one that is not an insumo
("Emplatar"). Discarding the draft SHALL leave the existing assignment untouched.

#### Scenario: Propose without writing

- **WHEN** the user presses "Sugerir desde la receta"
- **THEN** the client fetches the suggestion for the product and the active branch and shows the
  implied stations with their task lists filled in
- **AND** no mapping is created or updated

#### Scenario: Confirm saves the edited draft, not the raw suggestion

- **WHEN** the user edits a prefilled task list — adding "Emplatar", which is not an insumo — and
  confirms
- **THEN** the saved mapping holds the edited list

#### Scenario: A station already assigned is reconciled, not duplicated

- **WHEN** the draft includes a station the product is already mapped to
- **THEN** confirming updates that mapping's tasks instead of attaching it a second time

#### Scenario: Discard

- **WHEN** the user discards the draft
- **THEN** the draft disappears and the existing assignment is unchanged

#### Scenario: A dish with no recipe

- **WHEN** the suggestion comes back empty because the dish has no recipe items
- **THEN** the panel says there is nothing to derive and manual assignment stays available

### Requirement: The panel surfaces recipe drift and insumos without a station

When a suggestion has been fetched, the panel SHALL show, on each already-saved station, the
divergence the suggestion reports: tasks the recipe now implies that the saved mapping lacks, and
saved tasks the recipe no longer implies. The notice is informational — it SHALL never rewrite the
saved mapping, because a task list legitimately contains steps that are not insumos.

The panel SHALL also name the insumos of the recipe that contribute to no station of this branch,
marking those whose default station belongs to another branch, and point at the inventory board
where a station is given to them.

#### Scenario: Recipe changed under a saved mapping

- **WHEN** the suggestion reports tasks missing from, or no longer implied by, a saved mapping
- **THEN** that station shows a drift notice naming both sets
- **AND** the saved mapping is left untouched

#### Scenario: In sync

- **WHEN** the suggestion reports no divergence
- **THEN** no drift notice is rendered

#### Scenario: Insumos with no station are named

- **WHEN** the suggestion returns unassigned ingredients
- **THEN** the panel lists them, marks the ones whose default station is in another branch, and
  points to the inventory board
