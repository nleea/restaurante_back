# business-profile Specification

## Purpose
TBD - created by archiving change business-profile-and-hours. Update Purpose after archive.
## Requirements
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

### Requirement: Business profile identity is editable

The system SHALL allow an authorized user to update the business identity through the profile: tenant-level fields (name, tax id, email, phone) and per-branch details (address, phone). The update SHALL validate inputs and persist to the existing tenant and branch records.

#### Scenario: Edit tenant identity

- **WHEN** an authorized user updates the business name/tax id/email/phone
- **THEN** the values are persisted and returned by the next profile read

#### Scenario: Edit a branch's details

- **WHEN** an authorized user updates a branch's address/phone in the profile
- **THEN** that branch's details are persisted and returned by the next profile read

#### Scenario: Unauthorized edit rejected

- **WHEN** a user without `menu.manage` attempts to update the profile
- **THEN** the request is rejected and nothing is persisted

### Requirement: Business photo is editable through the profile

The profile update SHALL accept a business photo URL and persist it as the shared brand logo (the value the storefront reads), so changing the photo in the profile is reflected on the public storefront.

#### Scenario: Set the business photo

- **WHEN** an authorized user saves the profile with a new photo URL
- **THEN** the photo is stored as the brand logo and returned by the next profile read

#### Scenario: Storefront reflects the photo

- **WHEN** the business photo is changed via the profile
- **THEN** the storefront's brand logo shows the new photo

