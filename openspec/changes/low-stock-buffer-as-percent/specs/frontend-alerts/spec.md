## ADDED Requirements

### Requirement: The rule screen states each buffer's unit

The rule configuration screen SHALL state, for every rule, the unit its recovery buffer is measured
in, and SHALL NOT present a bare number. A buffer whose unit is not stated is a value nobody can
set correctly.

#### Scenario: The low-stock buffer is shown as a percentage

- **WHEN** the low-stock rule is configured
- **THEN** its recovery buffer is presented as a percentage of the ingredient's minimum

#### Scenario: A rule measured in time says so

- **WHEN** a rule whose buffer is measured in minutes is configured
- **THEN** the screen states that unit

#### Scenario: The effect is stated in words

- **WHEN** the low-stock buffer is shown
- **THEN** the screen explains that the alert clears once stock passes the minimum by that
  percentage
