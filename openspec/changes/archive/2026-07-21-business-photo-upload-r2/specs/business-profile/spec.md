## ADDED Requirements

### Requirement: Business photo is editable through the profile

The profile update SHALL accept a business photo URL and persist it as the shared brand logo (the value the storefront reads), so changing the photo in the profile is reflected on the public storefront.

#### Scenario: Set the business photo

- **WHEN** an authorized user saves the profile with a new photo URL
- **THEN** the photo is stored as the brand logo and returned by the next profile read

#### Scenario: Storefront reflects the photo

- **WHEN** the business photo is changed via the profile
- **THEN** the storefront's brand logo shows the new photo
