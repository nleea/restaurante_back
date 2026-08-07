## MODIFIED Requirements

### Requirement: Recovery hysteresis

An alert SHALL re-arm only when its condition has cleared past the rule's recovery buffer, not
merely when it returns to the threshold. The recovery buffer SHALL NOT be configurable to zero.

Each rule SHALL define the unit its recovery buffer is measured in. Where a rule's subjects do not
share a unit of measure, its buffer SHALL be relative rather than absolute, since no single
absolute quantity can be correct across incommensurable subjects.

#### Scenario: Returning to the threshold does not re-arm

- **WHEN** a low-stock alert's stock returns exactly to its minimum
- **THEN** the alert does not re-arm

#### Scenario: Clearing past the buffer re-arms

- **WHEN** stock rises past the minimum by more than the rule's recovery buffer
- **THEN** the alert resolves and the rule re-arms for that subject

#### Scenario: Oscillation produces one alert

- **WHEN** a value crosses the threshold repeatedly without ever clearing the buffer
- **THEN** exactly one alert was fired and no further notifications were sent

#### Scenario: Zero buffer is refused

- **WHEN** a rule is configured with a recovery buffer of zero
- **THEN** the configuration is rejected

#### Scenario: A rule whose subjects share no unit uses a relative buffer

- **WHEN** a rule's subjects are measured in different units from one another
- **THEN** its recovery buffer is applied as a proportion, not as a fixed quantity

### Requirement: Low stock rule

The system SHALL provide a low-stock rule evaluating a branch's stock against the existing
per-ingredient minimum, with the alert's subject being the ingredient. It SHALL NOT introduce a
second stock threshold alongside the existing minimum.

Its recovery buffer SHALL be a percentage of that ingredient's own minimum, because ingredients
carry independent units of measure and a fixed quantity would mean a different thing for each one.

#### Scenario: Crossing the minimum fires

- **WHEN** an ingredient's stock falls below its configured minimum on an enabled branch
- **THEN** an alert fires naming that ingredient

#### Scenario: Each ingredient is its own subject

- **WHEN** two ingredients fall below their minimums
- **THEN** two alerts exist, one per ingredient

#### Scenario: No ingredient minimum, no alert

- **WHEN** an ingredient has no configured minimum
- **THEN** it never fires a low-stock alert

#### Scenario: Recovery is proportional to the ingredient's own minimum

- **WHEN** two ingredients with very different minimums are each restocked by the same percentage
  above their minimum
- **THEN** both alerts resolve

#### Scenario: A small minimum does not demand a large restock

- **WHEN** an ingredient with a small minimum is restocked just over its buffer percentage
- **THEN** its alert resolves, without requiring a fixed quantity unrelated to its scale
