## MODIFIED Requirements

### Requirement: Thread view and reply

Selecting a conversation SHALL show its full thread in order, distinguishing messages from the
contact, from employees, and from the system, and SHALL show which employee sent each staff
reply. A user with `messaging.attend` SHALL be able to write and send a reply from the thread.

A message carrying an image SHALL render the image inline, at a size that lets the agent read a
payment receipt without leaving the inbox, and SHALL open it full-size on demand. A message
carrying a PDF SHALL offer to open it. A message whose file could not be retrieved SHALL say so
rather than appearing empty or broken.

#### Scenario: Thread shows both sides

- **WHEN** a conversation with inbound and outbound messages is opened
- **THEN** the thread renders them in order, visually distinguishing who sent each

#### Scenario: Sending a reply appends it

- **WHEN** an attending employee sends a reply
- **THEN** it appears in the thread attributed to them

#### Scenario: A failed reply is visible

- **WHEN** a reply could not be delivered
- **THEN** it stays in the thread marked as failed, so the agent knows it did not land

#### Scenario: An image is readable in the thread

- **WHEN** the customer sent a photo
- **THEN** the thread renders it inline, large enough to read a receipt, and opens it full-size on
  demand

#### Scenario: A PDF is offered, not embedded

- **WHEN** the customer sent a PDF
- **THEN** the thread offers to open it

#### Scenario: A caption reads as the message

- **WHEN** the customer's photo carried a caption
- **THEN** the caption is the message text, with the image below or beside it

#### Scenario: A file that could not be retrieved says so

- **WHEN** a message arrived with a file that could not be fetched
- **THEN** the thread states that a file arrived and could not be retrieved, with no broken image
