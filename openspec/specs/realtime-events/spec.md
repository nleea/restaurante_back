# realtime-events

## Purpose

A shared realtime foundation: a topic-scoped, per-branch event publisher and a
Server-Sent Events stream that lets browsers subscribe to a topic's changes for a
branch. Publishing is best-effort so a broker outage never fails a business
operation, and streams degrade to heartbeats-only rather than erroring, so clients
fall back to polling. Tenant/branch-isolated and gated by each topic's read
permission.

## Requirements

### Requirement: Topic-scoped, per-branch event publishing

The system SHALL provide a shared event publisher that broadcasts a change to a **topic**, scoped to a tenant and branch, so any subscriber of that topic for that branch is notified. Publishing SHALL be **best-effort**: a broker outage or publish failure SHALL be swallowed (logged) and SHALL NOT fail or roll back the business operation that produced the change. A published event SHALL only reach subscribers of the same topic, tenant, and branch.

#### Scenario: A change is broadcast to its topic and branch
- **WHEN** a mutation publishes an event for a topic on a branch
- **THEN** subscribers of that topic for that branch are notified

#### Scenario: A broker outage does not fail the operation
- **WHEN** the broker is unavailable and a mutation publishes an event
- **THEN** the publish is a no-op that is logged, and the mutation still succeeds

#### Scenario: Events are isolated by tenant and branch
- **WHEN** an event is published for branch A
- **THEN** subscribers for branch B (or another tenant) do not receive it

### Requirement: Server-sent event stream per topic and branch

The system SHALL expose the events of a topic for a branch as a Server-Sent Events stream a browser can consume over HTTP with a bearer token. The stream SHALL emit periodic heartbeats so intermediaries keep the connection open. When the broker is unreachable, the stream SHALL degrade to **heartbeats only** (staying open) rather than erroring, so the client silently relies on its polling fallback. Each stream SHALL be scoped to the caller's tenant and the requested branch, and gated by the topic's read permission.

#### Scenario: A subscriber receives events as they happen
- **WHEN** a client is streaming a topic for a branch and a matching event is published
- **THEN** the client receives that event on the stream

#### Scenario: The stream stays warm with heartbeats
- **WHEN** no events occur for a while
- **THEN** the stream still emits heartbeats and stays open

#### Scenario: The stream survives a broker outage
- **WHEN** the broker is unreachable while a client is connected
- **THEN** the stream keeps emitting heartbeats and does not error, and resumes delivering events when the broker returns

#### Scenario: Streaming requires the topic's read permission
- **WHEN** a client without the topic's read permission opens the stream
- **THEN** the request is rejected
