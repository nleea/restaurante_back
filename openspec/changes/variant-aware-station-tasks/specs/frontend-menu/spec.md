## ADDED Requirements

### Requirement: The task editor keeps each task's ingredient

The stations panel SHALL edit a mapping's tasks as a **list of rows**, one per task, rather than a
single comma-separated field. A derived row SHALL keep the ingredient it came from even when its
label is renamed, because that link is what lets the kitchen resolve the amount for the variant
that was actually ordered.

A person SHALL be able to add a free-text row (a step that is not an insumo) and remove any row.

#### Scenario: Renaming a derived task keeps its ingredient
- **WHEN** a user renames a derived row from "Carne de res" to "Carne" and saves
- **THEN** the saved task keeps its ingredient, so the amount still resolves per variant

#### Scenario: Add a step that is not an insumo
- **WHEN** a user adds a row typing "Emplatar"
- **THEN** it is saved as a task with no ingredient and reaches every variant verbatim

#### Scenario: Remove a task
- **WHEN** a user removes a row and saves
- **THEN** the task is gone from the mapping

#### Scenario: The panel shows the amount it will produce
- **WHEN** a derived row is displayed
- **THEN** its amount is shown in the kitchen's unit, matching what the ticket will say

### Requirement: A recipe line can be sent to a specific station

The recipe editor SHALL let an authorized user pick, per recipe line, the kitchen station that
line is worked at, with the ingredient's default preselected and a way to fall back to it.

#### Scenario: Override a line's station
- **WHEN** a user picks a station on a recipe line
- **THEN** it is saved on the line and the derivation proposes that station for this dish

#### Scenario: Fall back to the default
- **WHEN** a user clears the line's station
- **THEN** the line falls back to the ingredient's default
