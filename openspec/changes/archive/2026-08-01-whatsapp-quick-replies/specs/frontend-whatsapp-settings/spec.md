## ADDED Requirements

### Requirement: The settings screen edits quick replies

The WhatsApp settings screen SHALL provide a section for managing quick replies, listing each
entry with its name and text, allowing entries to be created, edited, deleted and reordered, and
saving them together with the rest of the autoreply settings.

#### Scenario: Creating an entry

- **WHEN** a manager adds a quick reply, fills in its name and text and saves
- **THEN** the entry is persisted and shown on the next load

#### Scenario: Reordering an entry

- **WHEN** a manager moves an entry up or down
- **THEN** the displayed order changes and the new order is what gets saved

#### Scenario: Deleting an entry

- **WHEN** a manager deletes an entry and saves
- **THEN** the entry is gone on the next load and does not reappear

### Requirement: The section explains that quick replies do not answer by themselves

The quick replies section SHALL state that these texts are inserted by a person into the composer
and are never sent automatically, so a manager does not confuse them with the keyword FAQs shown
elsewhere on the same screen.

#### Scenario: The distinction is visible without opening an entry

- **WHEN** a manager opens the quick replies section
- **THEN** help text states that quick replies never reply on their own

### Requirement: Suggested quick replies can be seeded

When the tenant has never configured quick replies, the section SHALL offer a set of suggested
entries and an explicit action to adopt them. Adopting them SHALL fill the editor without saving,
so the manager can edit or discard them before committing.

#### Scenario: Suggestions are offered to an unconfigured tenant

- **WHEN** a tenant that has never saved quick replies opens the section
- **THEN** the suggested entries are offered together with an action to adopt them

#### Scenario: Adopting does not save by itself

- **WHEN** a manager adopts the suggestions and leaves without saving
- **THEN** nothing is persisted and the tenant is still unconfigured

### Requirement: Invalid quick replies are reported before saving

The section SHALL block saving and explain the problem when a quick reply has an empty name, an
empty text, a text over the length limit, or a placeholder marker in braces.

#### Scenario: A placeholder is caught in the editor

- **WHEN** a manager types `{link}` into a quick reply text
- **THEN** the section reports that quick replies do not interpolate markers and saving is blocked

#### Scenario: An over-long text is caught in the editor

- **WHEN** a quick reply text exceeds the length limit
- **THEN** the section reports it and saving is blocked
