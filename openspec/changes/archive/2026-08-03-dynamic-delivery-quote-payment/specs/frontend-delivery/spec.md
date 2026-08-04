## ADDED Requirements

### Requirement: Manage kilometer delivery tariffs
The delivery administration screen SHALL let a user with `delivery.manage` create, edit and view
the active branch's ordered kilometer tariff bands and their fees. It SHALL show the maximum
covered distance and prevent saving invalid band arrangements; users without that permission see
the configured plan without write controls.

#### Scenario: Manager changes a band fee
- **WHEN** a manager changes the fee for the band ending at 4 km and saves a valid plan
- **THEN** future quotes use that fee while already quoted orders retain their prior fee

#### Scenario: Read-only delivery user sees pricing
- **WHEN** a user has `delivery.read` but not `delivery.manage`
- **THEN** they can see the active kilometer bands but cannot modify them

### Requirement: Surface quote and payment-request operations
The dispatch surface SHALL show each delivery's quote status, adjusted distance and frozen fee when
available, plus whether its payment request was sent, failed or needs operational follow-up.

#### Scenario: Dispatcher sees an unquoted delivery
- **WHEN** a delivery awaits geocoding or distance calculation
- **THEN** its row clearly states that it is pending quote instead of showing a zero fee as final

#### Scenario: Dispatcher sees a failed message emission
- **WHEN** a quoted delivery's WhatsApp payment-request emission fails
- **THEN** its row identifies the failure and offers the authorized operational retry/follow-up
