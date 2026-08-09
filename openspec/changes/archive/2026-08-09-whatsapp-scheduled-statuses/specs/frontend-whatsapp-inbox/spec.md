## ADDED Requirements

### Requirement: The thread can opt a contact out of statuses

The thread view SHALL let whoever is attending it mark the contact as not wanting to receive
statuses, and unmark it, gated by `messaging.attend`. The current setting SHALL be visible in the
thread.

The control belongs here and not on the statuses screen: the request arrives **in the chat**, and the
person who reads it is the person attending. Requiring a change of screen and of permission to honour
a request just read is how the request goes unhonoured.

Marking a contact SHALL NOT change the conversation's state, remove it from the inbox, or affect
replying to it.

#### Scenario: An attendant honours the request where they read it

- **WHEN** a contact writes asking not to receive statuses and the attendant marks them
- **THEN** the contact is excluded from future status audiences, and the thread is otherwise unchanged

#### Scenario: The setting is visible

- **WHEN** a thread of an opted-out contact is opened
- **THEN** the thread shows that this contact does not receive statuses

#### Scenario: It can be undone

- **WHEN** an opted-out contact is unmarked
- **THEN** they are eligible for future status audiences again

#### Scenario: Replying still works

- **WHEN** a contact is opted out
- **THEN** the composer behaves exactly as before and the reply is sent

#### Scenario: Without the permission the control is absent

- **WHEN** a user without `messaging.attend` views a thread
- **THEN** the control is not offered
