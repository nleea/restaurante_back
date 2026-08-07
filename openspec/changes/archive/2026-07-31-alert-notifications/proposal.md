## Why

The system knows things nobody is told. Stock crosses its minimum and the only way to find
out is to open the inventory board. A WhatsApp session drops and the branch goes mute with no
signal — a gap `whatsapp-channel` documented and deliberately left open. The caja is still
open at 2am. In every case the data is already there and the person who needs it is not
looking.

This is not an AI problem. `InventoryRepository.list_low_stock` already exists; the shape of
the solution already exists too, in `delivery/infrastructure/worker.py`, whose own docstring
states it: **the job is the latency, the cron sweep is the guarantee.**

The hard part is not detecting. It is **not becoming noise**. A naive implementation messages
the same low tomato every five minutes until someone mutes it, and then the module is dead
and nobody notices the next real alert. That is why this change models an alert as an entity
with a lifecycle rather than a notification as an event.

`assistant-core` depends on this: the "80% of your quota is spent" warning is just another
rule on this machinery, with the same hysteresis. Building alerts first is what keeps that
from being reinvented. See `docs/messaging/ROADMAP.md`.

## What Changes

- **`AlertRule` and `Alert` with a real lifecycle.** A rule is a configured condition for a
  branch; an alert is an instance of that rule firing.

```
   armed ──▶ fired ──▶ acknowledged ──▶ resolved ──▶ armed
                                            │
                             re-arms only past the recovery buffer
```

- **Hysteresis is mandatory, not optional.** A fired alert does not fire again. It re-arms
  only when the condition clears past a configured recovery buffer — stock back above
  `min + buffer`, not merely back to `min` — so a value oscillating on the threshold produces
  one alert, not forty.
- **Job plus cron sweep**, copied from the delivery worker. The job is announced on the
  triggering mutation and gives seconds-level latency; the cron sweep is authoritative and
  finds everything the job missed — Redis down, job died, a code path that forgot to announce.
  The sweep is the guarantee and the system is correct without the job.
- **`NotificationChannel` port with two adapters.** In-app realtime first, WhatsApp for
  escalation. Alerts do not import the messaging module; the composition root wires the
  adapter, so `alert-notifications` works with WhatsApp entirely absent.
- **Three rules to start**: low stock (per branch, per ingredient, threshold from the existing
  `min_stock`), WhatsApp session disconnected, and cash session still open past a configured
  hour.
- **Acknowledgement is explicit and attributed.** Someone takes an alert; everyone else sees
  who. An unacknowledged alert escalates to WhatsApp after a configured delay — that delay is
  the only reason to spend an outbound message on staff.
- **An alerts screen** listing what is firing for the active branch, with acknowledge and a
  per-rule configuration view.

Out of scope: the quota rule (registered by `assistant-core` on this machinery), anything
involving an LLM, alert rules driven by free-text conditions, and per-employee routing beyond
"the branch's staff with the permission".

## Capabilities

### Added Capabilities
- `alert-notifications`: alert rules and alert instances with an armed/fired/acknowledged/
  resolved lifecycle and mandatory recovery hysteresis; an arq worker running announced jobs
  for latency and an authoritative cron sweep for the guarantee; a `NotificationChannel` port
  with realtime and WhatsApp adapters; low-stock, WhatsApp-session-down and caja-left-open
  rules; explicit attributed acknowledgement with delayed escalation.
- `frontend-alerts`: a branch-scoped alerts panel showing what is firing, who acknowledged
  what, and a per-rule configuration screen with thresholds, recovery buffers and escalation
  delays.

## Impact

- **Backend**: new `modules/alerts/` following the module layout (`domain/{entities,ports}`,
  `application/use_cases`, `infrastructure/{models,repositories,api,worker}`); migration adding
  `alert_rules` and `alerts`.
- **Second arq worker.** The delivery worker must stay a single process because of its
  provider rate limits; this one has no such constraint but its cron sweep must not run twice
  concurrently. It is a separate worker with its own settings, not a second queue on the
  delivery worker.
- **Cross-module reads**: alerts evaluates conditions by reading inventory, messaging sessions
  and cash. Read-only, through the existing repositories, with no writes back.
- **New permissions**: `alerts.read` and `alerts.manage`.
- **Frontend**: alerts panel and rule configuration; a badge on the existing nav.
- **Operational**: escalation to WhatsApp sends outbound to staff. It is bounded by the
  escalation delay and by acknowledgement, and it goes to employees who are saved contacts —
  but it is the first automated outbound to non-customers and it raises the number's exposure.
- **Not breaking**: nothing existing changes behaviour; with every rule disabled the system is
  as it was.
