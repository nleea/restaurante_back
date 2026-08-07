## ADDED Requirements

### Requirement: Structured operating hours per branch

The system SHALL store structured operating hours per branch as weekly windows (per weekday: closed, or one or more open/close time windows, including windows that cross midnight). The hours SHALL support computing whether the branch is within opening hours at a given time and the next opening time.

#### Scenario: Compute next opening

- **WHEN** the current time is outside a branch's configured windows
- **THEN** the system can report the next weekday/time the branch opens

#### Scenario: Overnight window

- **WHEN** a window's close time is earlier than its open time (crosses midnight)
- **THEN** it is treated as spanning into the next day

#### Scenario: Closed day

- **WHEN** a weekday is marked closed
- **THEN** it contributes no open window and is skipped when computing the next opening

### Requirement: Consolidated business profile

The system SHALL expose a business profile that aggregates tenant-level identity (name, photo/logo, tax id, email) and per-branch details (address, phone, operating hours), and references the existing staff roster without duplicating it. The profile SHALL be the single source of truth for the business name and photo.

#### Scenario: Read the profile

- **WHEN** the business profile is requested
- **THEN** it returns the tenant identity, the branch details including structured hours, and a reference to staff

#### Scenario: Name and photo are single-sourced

- **WHEN** the business name or photo is updated in the profile
- **THEN** the storefront reflects the updated value without a separate appearance copy to keep in sync
