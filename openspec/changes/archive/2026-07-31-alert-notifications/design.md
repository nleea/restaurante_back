## Context

Three ingredients already exist and this change assembles them:

- **The detection query.** `InventoryRepository.list_low_stock(tenant, branch)` is already in
  the inventory port.
- **The worker pattern.** `delivery/infrastructure/worker.py` documents it precisely: a job
  announced on a mutation gives latency and may be lost; a cron sweep over the authoritative
  condition gives the guarantee and finds "every pin-less record whether or not a job was ever
  enqueued". The same split applies exactly.
- **The delivery mechanism.** `EventPublisher` for in-app realtime, and after
  `whatsapp-channel`, a gateway for WhatsApp.

What does not exist is the part that decides *whether to speak*. That is the whole design.

## Goals / Non-Goals

**Goals:**
- Detect a condition reliably, whether or not anything announced it.
- Tell someone once, not repeatedly.
- Make "who is handling this" visible.
- Work with the LLM absent and with WhatsApp absent.

**Non-Goals:**
- Free-text or user-authored rule conditions. Rules are code with configured thresholds.
- Per-employee routing, on-call rotations, or schedules.
- The quota rule — `assistant-core` registers it on this machinery.
- Historical analytics on alerts. The table is a record, not a reporting surface, yet.

## Decisions

**1. The alert is an entity with a lifecycle; the notification is only its transport.**

```
   armed ──▶ fired ──▶ acknowledged ──▶ resolved ──▶ armed
```

Modelling "notification" instead means having no place to record that the tomato is still low
and we already said so. Every property that keeps this module alive — dedupe, hysteresis,
acknowledgement, escalation — hangs off the state, not off the message.

**2. Hysteresis is mandatory and asymmetric.**
An alert fires at the threshold and re-arms only past `threshold + recovery_buffer`. Symmetric
thresholds mean a value hovering at the boundary re-fires on every evaluation. The buffer is
per rule with a sane default; there is no way to configure it to zero, because zero is the bug
this exists to prevent.
*Alternative considered:* a cooldown timer (`don't re-fire for 30 minutes`). Rejected — a
timer re-fires on a condition that never recovered, which is the same noise delayed. A buffer
is a statement about the world; a timer is a statement about the clock.

**3. Job for latency, cron sweep for the guarantee — the sweep is authoritative.**
Copied from the delivery worker deliberately, including its stance: **the system must be
correct with the job path entirely removed.** The job is announced on a stock movement and
evaluates one ingredient; the sweep evaluates every enabled rule for every branch on a fixed
interval. If Redis is down, if the job dies, if a code path forgets to announce — the sweep
still fires the alert, late but certain.
*Consequence:* the sweep must not run concurrently with itself. `max_jobs` is not enough
across processes, so "run exactly one alerts worker" is a deployment requirement, stated here
rather than left as a knob.

**4. Firing is claimed atomically, so job and sweep cannot both fire it.**
The transition `armed → fired` is a conditional update on the alert row (`WHERE status =
'armed'`). Whoever wins sends; the loser does nothing. This is the same emit-once shape as the
autoreply's emissions and the inbox's claim — three occurrences of one idea, deliberately
kept the same shape.

**5. `NotificationChannel` is a port, so alerts never import messaging.**
The dependency arrow points out of `alerts`, never into it. The composition root injects the
realtime adapter always and the WhatsApp adapter only when the channel exists and the rule
escalates. `alert-notifications` is therefore shippable and testable before, during or
without WhatsApp.

**6. In-app first, WhatsApp only on escalation.**
Realtime costs nothing, arrives instantly, and cannot get a phone number banned. WhatsApp is
spent only on an alert nobody acknowledged within the escalation delay. This keeps automated
outbound to staff rare and tied to something genuinely ignored.
*Alternative considered:* WhatsApp immediately for critical rules. Rejected for now — "which
rules are critical" is a judgement nobody has data for yet, and the escalation delay expresses
the same intent without a second concept.

**7. Rules are code with configured parameters, not user-authored conditions.**
Each rule is a small evaluator with a stable identifier; tenants configure enablement,
threshold, recovery buffer and escalation delay. A rule engine over free-text conditions is a
product in itself and would be the wrong risk to take on the first three rules.

**8. Low stock reuses `min_stock`; it does not introduce a second threshold.**
The inventory module already carries `min_stock` per (branch, ingredient) and
`list_low_stock`. The rule adds the recovery buffer and nothing else. Two thresholds for one
concept would drift within a month.

**9. Acknowledgement is attributed and visible.**
An acknowledged alert names who took it, so the second person to see it does not duplicate the
work — the same failure the shared inbox's claim solves, applied to alerts.

## Risks / Trade-offs

- **Two workers to operate.** The delivery worker must be a singleton for provider rate
  limits; this one must be a singleton so the sweep does not overlap. Two "run exactly one"
  processes is an operational burden and an easy thing to get wrong on a scaled deployment.
- **Sweep interval is a latency floor.** With the job path lost, an alert arrives at worst one
  sweep late. Chosen deliberately: certain-and-late beats fast-and-missing.
- **Escalation to WhatsApp is outbound to staff.** Bounded by delay and acknowledgement, sent
  only to saved employee contacts, but it is automated outbound and it raises exposure on an
  unofficial bridge.
- **Alert fatigue can still happen through configuration.** A tenant that sets thresholds badly
  will drown. Hysteresis prevents the mechanical version of the problem; it cannot prevent a
  bad threshold.
- **The session-down rule depends on a status that can lie.** `whatsapp-channel` records
  session status from bridge signals; between a real disconnection and the signal, the rule
  sees `connected`. This rule narrows that gap; it does not close it.

## Migration Plan

Alembic migration `0023_alerts`:

- `alert_rules` (branch-scoped): `rule_key`, `is_enabled`, `threshold` (nullable, rule-defined
  meaning), `recovery_buffer`, `escalation_after_minutes`, `escalate_to_whatsapp`
- `alerts` (branch-scoped): `rule_key`, `subject_ref` (the ingredient, session or cash session
  the alert is about), `status`, `fired_at`, `acknowledged_at`, `acknowledged_by`,
  `resolved_at`, `escalated_at`, with a unique constraint on
  `(tenant, branch, rule_key, subject_ref)` for the open instance

No backfill. Rules are seeded disabled, so nothing fires until a tenant turns them on.

## Open Questions

- **Should a resolved alert be kept or deleted?** Kept for now — "how often did we run out of
  tomato" is the report somebody will ask for. It also means the table grows and will need a
  retention policy before this sees a year of production.
- **What is the right sweep interval?** Five minutes is the starting guess. Low stock does not
  need seconds; a mute WhatsApp branch arguably does. Possibly per-rule intervals later.
- **Should escalation notify a specific role or everyone with the permission?** Currently
  everyone with `alerts.read` on the branch. A `manager` notion does not exist yet.
