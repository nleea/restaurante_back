## ADDED Requirements

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
