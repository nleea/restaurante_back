## ADDED Requirements

### Requirement: Send a delivery payment request to a reachable contact
The messaging system SHALL send a message identifying the order, its final total and the secure
payment link when a delivery payment request is created and the order is linked to a reachable
WhatsApp contact. It SHALL record whether the emission succeeded, failed or is pending and SHALL
NOT change the quote, payment or kitchen state if messaging fails.

#### Scenario: Quote emits one WhatsApp request
- **WHEN** a quoted delivery has a linked reachable WhatsApp contact
- **THEN** the system sends one payment-request message for that quote and records its emission

#### Scenario: No reachable WhatsApp contact
- **WHEN** a quoted delivery has no linked reachable WhatsApp contact
- **THEN** the quote remains valid, no unsolicited message is sent, and the payment request is
  surfaced for operational follow-up

### Requirement: Emission happens where the link is still readable
The system SHALL send a payment request only while its single-use token is still in clear text,
because only its hash is persisted. A failed or unsent emission SHALL therefore be recovered by
issuing a NEW payment request — invalidating the previous one — and never by attempting to resend
the previous link.

#### Scenario: Operator recovers a failed emission
- **WHEN** an authorized user retries a payment request whose WhatsApp emission failed
- **THEN** the system issues a new single-use request for the same unchanged quote, invalidates the
  previous request, and sends the new link

#### Scenario: A stored request cannot be resent
- **WHEN** any code path attempts to build a payment link from a persisted request
- **THEN** no usable link can be produced, because the stored request holds only the token hash
