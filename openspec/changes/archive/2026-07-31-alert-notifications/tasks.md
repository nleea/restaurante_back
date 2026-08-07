> The WhatsApp escalation adapter needs `whatsapp-channel`. Everything else stands alone —
> build and ship without it if that change is not applied yet.

## 1. Backend — module scaffold and schema

- [x] 1.1 Create `modules/alerts/` following the standard layout
      (`domain/{entities,ports}`, `application/use_cases`, `infrastructure/{models,repositories,api,worker}`)
- [x] 1.2 `AlertRuleModel` (`BranchScopedMixin`): `rule_key`, `is_enabled`, `threshold`
      (nullable), `recovery_buffer`, `escalation_after_minutes`, `escalate_to_whatsapp`;
      `UNIQUE(tenant_id, branch_id, rule_key)`
- [x] 1.3 `AlertModel` (`BranchScopedMixin`): `rule_key`, `subject_ref`, `status`, `fired_at`,
      `acknowledged_at`, `acknowledged_by`, `resolved_at`, `escalated_at`; partial unique on
      the open instance per `(tenant, branch, rule_key, subject_ref)`
- [x] 1.4 Domain entities `AlertRule`, `Alert`; register models in `shared/models_registry.py`
- [x] 1.5 Alembic migration `0024_alerts` (la 0023 la ocupa whatsapp-autoreply); up/down en Postgres
- [x] 1.6 Reglas materializadas al leer (`GET /alerts/rules` devuelve las conocidas,
      apagadas) — no hace falta sembrar en el aprovisionamiento

## 2. Backend — lifecycle

- [x] 2.1 `fire(rule_key, subject_ref)` — atomic `armed → fired` (conditional update); returns
      whether this caller won, and only the winner notifies
- [x] 2.2 `acknowledge(alert_id, employee_id)` — records who and when; conflict when already
      acknowledged, naming the holder
- [x] 2.3 `resolve(alert_id)` — only when the condition has cleared past the recovery buffer
- [x] 2.4 Reject a rule configuration with a zero recovery buffer (domain-level, not just UI)
- [x] 2.5 Enforce at most one open alert per `(branch, rule_key, subject_ref)`

## 3. Backend — rule evaluators

- [x] 3.1 `AlertRuleEvaluator` protocol: given tenant/branch/config, yield subjects that should
      fire and subjects that have cleared past the buffer
- [x] 3.2 Low stock — reuse `InventoryRepository.list_low_stock` and the existing `min_stock`;
      subject is the ingredient; no second threshold introduced
- [x] 3.3 WhatsApp session down — subject is the branch's session; inert when no sessions exist
- [x] 3.4 Cash session left open past a configured hour — subject is the cash session
- [x] 3.5 Registry mapping `rule_key` → evaluator, so `assistant-core` can register the quota
      rule later without touching this module

## 4. Backend — notification port

- [x] 4.1 `NotificationChannel` port (`notify(tenant, branch, alert, kind)`)
- [x] 4.2 Realtime adapter over the existing `EventPublisher`; best-effort, never raises
- [x] 4.3 WhatsApp adapter over the channel's guarded gateway, wired only when available
- [x] 4.4 Composition root injects realtime always, WhatsApp optionally — no import of
      `messaging` from `alerts`

## 5. Backend — worker

- [x] 5.1 `alerts/infrastructure/worker.py` with its own `WorkerSettings`, separate from the
      delivery worker
- [x] 5.2 `evaluate_subject` job — announced on the triggering mutation, evaluates one subject
- [x] 5.3 `sweep_alert_rules` cron — evaluates every enabled rule for every tenant and branch;
      authoritative, correct with the job path removed
- [x] 5.4 `escalate_pending` pass — escalates alerts past their delay, at most once, recording
      `escalated_at`
- [x] 5.5 Document "run exactly one alerts worker" in the module docstring, with the reason
      (overlapping sweeps), mirroring the delivery worker's stance
- [x] 5.6 Announce the job from the stock movement path without making the mutation depend on
      the queue being up

## 6. Backend — API and permissions

- [x] 6.1 List open alerts for a branch; acknowledge; list and update rule configuration
- [x] 6.2 Add `alerts.read` and `alerts.manage` to `identity/domain/permissions_catalog.py`
- [x] 6.3 Gate endpoints; register the router in the app factory

## 7. Backend — tests

- [x] 7.1 Disabled rule never fires; per-branch enablement is independent
- [x] 7.2 Condition true fires once; persisting condition does not re-fire
- [x] 7.3 Hysteresis: returning to the threshold does not re-arm; clearing past the buffer does
- [x] 7.4 Oscillation across the threshold produces exactly one alert and one notification
- [x] 7.5 Zero recovery buffer rejected
- [x] 7.6 Job and sweep racing the same subject → one alert, one notification
- [x] 7.7 **Sweep is authoritative**: with the job path disabled entirely, the alert still fires
- [x] 7.8 Queue unavailable during a stock movement → mutation succeeds, sweep fires later
- [x] 7.9 Sweep covers all tenants and branches, not only recently active ones
- [x] 7.10 Acknowledgement attributed; second acknowledger gets a conflict naming the holder
- [x] 7.11 Escalation happens once past the delay; acknowledging first prevents it
- [x] 7.12 Escalation to an unreachable employee sends nothing but is still recorded
- [x] 7.13 Works with no WhatsApp channel present at all
- [x] 7.14 Channel outage does not lose the fired alert
- [x] 7.15 Low stock: per-ingredient subjects; ingredient without a minimum never fires
- [x] 7.16 Session-down fires and resolves on reconnect; cash-left-open fires and resolves on
      close
- [x] 7.17 Permission gating for read, acknowledge and manage

## 8. Frontend — panel

- [x] 8.1 Alerts panel route + store, scoped to the active branch
- [x] 8.2 Open alerts list with subject, time, acknowledgement state and holder; all-clear
      empty state
- [x] 8.3 Acknowledge action; losing the race shows the holder and refreshes
- [x] 8.4 Navigation indicator for unacknowledged alerts, updating off the doorbell with a
      polling fallback

## 9. Frontend — rule configuration

- [x] 9.1 Configuration screen gated on `alerts.manage`, listing every rule for the branch
- [x] 9.2 Enablement, threshold, recovery buffer, escalation delay, WhatsApp escalation
- [x] 9.3 Explain the recovery buffer in terms of the repetition it prevents; refuse zero
- [x] 9.4 WhatsApp escalation option explains when the branch has no connected session

## 10. Frontend — tests

- [x] 10.1 Panel lists only the active branch; all-clear state
- [x] 10.2 Acknowledgement attribution visible; losing the race explained
- [x] 10.3 Indicator appears on firing and clears when handled
- [x] 10.4 Zero recovery buffer refused in the UI
- [x] 10.5 Routes hidden and refused without their permissions

## 11. Quality gates

- [x] 11.1 Backend: `ruff`, `mypy --strict`, full `pytest` green (751)
- [x] 11.2 Frontend: lint, type-check, unit tests, production build green
- [x] 11.3 Despliegue: **`poetry run python -m scripts.seed`** — los permisos nuevos viven en
      `permissions_catalog.py` pero `require_permission` los busca en la tabla `permissions`.
      Sin este paso, `alerts.read`/`alerts.manage` no existen para nadie y la pantalla da 403.
      Idempotente y aditivo: no toca datos existentes.
      Verificado 2026-07-31: el catálogo menos lo que devuelve `/auth/me` del admin es el
      conjunto vacío en los dos tenants desplegados (`demo`, `demo2`), y `alerts.read` /
      `alerts.manage` están entre sus 44 permisos.
- [x] 11.4 Manual: drop an ingredient below its minimum, see the alert in seconds; stop the
      worker's job path and confirm the sweep still fires it
      Verificado 2026-07-31 contra el despliegue (`demo`): se bajó «Aceite vegetal» de 29.105
      a 3 (mínimo 4) **escribiendo directo en `inventory_stocks`**, es decir sin que ningún
      camino de la aplicación anunciara el job — el barrido la disparó igual, un segundo
      barrido no la duplicó (el índice único parcial hizo `DO NOTHING`, igual que con las dos
      alertas ya abiertas de Camarón y Ñame), y al restaurar el stock por encima de
      mínimo + colchón el barrido la cerró. El camino del job (alerta en segundos tras un
      movimiento de stock) ya se había comprobado el 2026-07-30 con «Azúcar», incluido el
      escalado a WhatsApp.
