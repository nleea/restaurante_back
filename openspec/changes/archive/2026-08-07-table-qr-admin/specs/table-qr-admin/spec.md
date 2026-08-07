## ADDED Requirements

### Requirement: A table's public URL is built in exactly one place

The system SHALL derive a table's public ordering URL from the tenant slug, the public storefront
domain, the branch code and the table code, in a single shared helper alongside the other public
links.

This URL is **printed**. A wrong WhatsApp link is fixed by sending another one; a wrong sticker
has to be peeled off ten tables, and the error is not discovered until a customer scans it. One
place to decide the shape is what keeps the paper and the router from disagreeing.

Both the branch code and the table code SHALL be percent-encoded, even though today's codes are
alphanumeric: whoever changes the alphabet later has no reason to know it travels in a path, and a
stray separator would silently split the route.

When no public domain is configured the helper SHALL return an empty string, the same contract the
other public links already follow — half a URL printed on a sticker is the worst outcome, because
it does not fail until someone scans it.

#### Scenario: The URL carries branch and table in the path
- **WHEN** a table's URL is built for a tenant, branch code and table code
- **THEN** it is the tenant's subdomain followed by the store path with both codes as segments

#### Scenario: Codes that would break the path are escaped
- **WHEN** either code contains a path separator
- **THEN** it is percent-encoded and the path keeps its expected number of segments

#### Scenario: No public domain yields no URL
- **WHEN** no public storefront domain is configured
- **THEN** the helper returns an empty string rather than a partial URL

### Requirement: Each table can produce its own QR

The system SHALL let an authorized user obtain the QR of a single dining table, returning both the
image and **the URL it encodes**.

Returning the URL is not redundancy. A QR is opaque by definition: if the only way to know where it
points were to scan it, nobody would check anything before sending ten stickers to print.

The image SHALL be SVG, because a sticker is enlarged for print and a bitmap prints at whatever
resolution it happened to have. It SHALL use high error correction, because the code lives glued to
a restaurant table that gets greasy and scratched — a denser drawing in exchange for still reading
with nearly a third of its area destroyed.

The endpoint SHALL be gated by the existing order-read permission and SHALL NOT introduce a new
permission code. The table code is not a secret — it is printed in plain sight of anyone who walks
in — so what is protected is access to the admin surface, not the datum. A new permission would
also need seeding, and an unseeded permission returns 403 to everyone.

#### Scenario: A table returns its QR and its URL
- **WHEN** an authorized user requests the QR of an existing table
- **THEN** an SVG and the URL it encodes are returned

#### Scenario: Refuse rather than print something that leads nowhere
- **WHEN** no public storefront domain is configured, or the table's branch has no public code, or
  the table has no code
- **THEN** the system responds with a validation error naming the reason, and returns no image

#### Scenario: Unknown table
- **WHEN** the QR of a table that does not exist in the tenant is requested
- **THEN** the system responds 404 Not Found

#### Scenario: Unauthorized access is refused
- **WHEN** a request arrives without the permission to read orders
- **THEN** the system refuses it and returns no image
