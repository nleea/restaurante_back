## ADDED Requirements

### Requirement: Perfil del negocio admin screen

The admin SHALL provide a "Perfil del negocio" screen to view and edit the business identity (name, photo, tax id, email), per-branch details (address, phone), and the structured operating hours, and to see the staff roster (referenced from the staff module).

#### Scenario: Edit identity and hours

- **WHEN** an authorized user edits the business name, photo, or a branch's operating hours
- **THEN** the changes are saved and reflected wherever the business identity/hours are read (including the storefront)

#### Scenario: Staff shown by reference

- **WHEN** the profile screen shows personnel
- **THEN** it lists the existing staff roster without duplicating staff records

### Requirement: Storefront closed state shows opening time

The storefront SHALL present a "cerrado · abrimos a las X" state when ordering is closed, using the next opening time from the structured hours.

#### Scenario: Customer sees when it reopens

- **WHEN** a customer opens the storefront while ordering is closed
- **THEN** they see a closed message with the next opening time
