## ADDED Requirements

### Requirement: Storefront exposes hours and next opening

The public storefront SHALL expose the business's structured operating hours and, when the caja is closed, the next opening time, so the customer-facing closed state can show "cerrado · abrimos a las X". The business name and photo shown SHALL be sourced from the business profile.

#### Scenario: Closed state shows next opening

- **WHEN** the storefront is loaded while the branch's caja is closed
- **THEN** it can display that ordering is closed and the next opening time from the structured hours

#### Scenario: Name and photo from the profile

- **WHEN** the storefront renders the business identity
- **THEN** the name and photo come from the business profile (single source), not a separate appearance copy
