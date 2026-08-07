"""Adaptador SQLAlchemy del repositorio de alertas.

Dos métodos hacen todo el trabajo interesante, y los dos son atómicos a propósito:

- `claim_fire` — el `INSERT` gana o choca contra el índice único parcial. Quien inserta,
  notifica; quien choca, calla. El job y el barrido pueden mirar el mismo tomate a la vez.
- `acknowledge` / `mark_escalated` — `UPDATE … WHERE <estado esperado>`, y se mira cuántas
  filas se tocaron. Leer-y-luego-escribir sería una carrera entre dos personas pulsando el
  mismo botón.

Es la misma forma que las emisiones del autoreply y la toma de conversación del inbox: tres
apariciones de una misma idea, mantenidas iguales a propósito.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy import or_ as sa_or
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.alerts.domain.entities import (
    ALERT_ACKNOWLEDGED,
    ALERT_FIRED,
    ALERT_RESOLVED,
    OPEN_ALERT_STATUSES,
    WHATSAPP_REESCALATION_HOURS,
    Alert,
    AlertRule,
)
from restaurante.modules.alerts.infrastructure.models import (
    OPEN_ALERT_PREDICATE,
    AlertModel,
    AlertRuleModel,
)
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel


def _as_utc(value: datetime) -> datetime:
    """Un instante siempre con zona.

    SQLite no guarda el offset y devuelve el `datetime` desnudo; Postgres sí lo conserva.
    Restar uno de cada tipo revienta, así que el borde se normaliza aquí — lo que se guardó
    era UTC (`datetime.now(UTC)`), y esto sólo se lo vuelve a decir a Python.
    """
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _to_rule(row: AlertRuleModel) -> AlertRule:
    return AlertRule(
        id=row.id,
        tenant_id=row.tenant_id,
        branch_id=row.branch_id,
        rule_key=row.rule_key,
        is_enabled=row.is_enabled,
        threshold=row.threshold,
        recovery_buffer=row.recovery_buffer,
        remind_every_minutes=row.remind_every_minutes,
        escalation_after_minutes=row.escalation_after_minutes,
        escalate_to_whatsapp=row.escalate_to_whatsapp,
    )


def _to_alert(row: AlertModel) -> Alert:
    return Alert(
        id=row.id,
        tenant_id=row.tenant_id,
        branch_id=row.branch_id,
        rule_key=row.rule_key,
        subject_ref=row.subject_ref,
        subject_label=row.subject_label,
        status=row.status,
        fired_at=row.fired_at,
        acknowledged_at=row.acknowledged_at,
        acknowledged_by=row.acknowledged_by,
        resolved_at=row.resolved_at,
        last_escalated_at=row.last_escalated_at,
        last_notified_at=row.last_notified_at,
        reminders_muted_at=row.reminders_muted_at,
    )


class SqlAlchemyAlertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reglas -------------------------------------------------------------
    async def list_rules(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[AlertRule]:
        stmt = select(AlertRuleModel).where(
            AlertRuleModel.tenant_id == tenant_id,
            AlertRuleModel.branch_id == branch_id,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_rule(row) for row in rows]

    async def get_rule(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, rule_key: str
    ) -> AlertRule | None:
        stmt = select(AlertRuleModel).where(
            AlertRuleModel.tenant_id == tenant_id,
            AlertRuleModel.branch_id == branch_id,
            AlertRuleModel.rule_key == rule_key,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_rule(row) if row else None

    async def save_rule(self, rule: AlertRule) -> AlertRule:
        stmt = select(AlertRuleModel).where(
            AlertRuleModel.tenant_id == rule.tenant_id,
            AlertRuleModel.branch_id == rule.branch_id,
            AlertRuleModel.rule_key == rule.rule_key,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = AlertRuleModel(
                tenant_id=rule.tenant_id,
                branch_id=rule.branch_id,
                rule_key=rule.rule_key,
            )
            self._session.add(row)
        row.is_enabled = rule.is_enabled
        row.threshold = rule.threshold
        row.recovery_buffer = rule.recovery_buffer
        row.remind_every_minutes = rule.remind_every_minutes
        row.escalation_after_minutes = rule.escalation_after_minutes
        row.escalate_to_whatsapp = rule.escalate_to_whatsapp
        await self._session.commit()
        await self._session.refresh(row)
        return _to_rule(row)

    async def list_enabled_rules(self) -> list[AlertRule]:
        # Sin filtro de tenant a propósito: el barrido corre sin contexto y debe ver a todos.
        # Acotarlo a los "activos recientemente" es exactamente cómo se pierde la sucursal
        # que lleva dos días muda — que es justo la que hay que avisar.
        stmt = select(AlertRuleModel).where(AlertRuleModel.is_enabled.is_(True))
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_rule(row) for row in rows]

    # --- Alertas ------------------------------------------------------------
    async def claim_fire(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject_ref: str,
        subject_label: str | None = None,
    ) -> Alert | None:
        """`None` cuando ya había una abierta: el otro evaluador llegó primero.

        `INSERT … ON CONFLICT DO NOTHING … RETURNING`, no un `INSERT` que revienta y se
        captura: una `IntegrityError` deja la transacción entera inservible y se llevaría por
        delante lo que disparó la evaluación —un movimiento de stock, el cierre de una caja—.
        Perder una carrera es lo NORMAL aquí, y lo normal no se implementa con excepciones.

        Misma forma que `try_claim_emission` en messaging.
        """
        dialect = self._session.bind.dialect.name if self._session.bind else "postgresql"
        insert = sqlite_insert if dialect == "sqlite" else pg_insert
        stmt = (
            insert(AlertModel)
            .values(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                branch_id=branch_id,
                rule_key=rule_key,
                subject_ref=subject_ref,
                subject_label=subject_label,
                status=ALERT_FIRED,
                fired_at=datetime.now(UTC),
            )
            # El índice es PARCIAL, así que hay que decirle a la base contra cuál está
            # chocando: sin el `index_where` no puede inferirlo y el conflicto no se captura.
            .on_conflict_do_nothing(
                index_elements=["tenant_id", "branch_id", "rule_key", "subject_ref"],
                index_where=OPEN_ALERT_PREDICATE,
            )
            .returning(AlertModel.id)
        )
        won = (await self._session.execute(stmt)).scalar_one_or_none()
        await self._session.commit()
        if won is None:
            return None
        return await self.get_by_id(tenant_id, won)

    async def list_open(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[Alert]:
        stmt = (
            select(AlertModel)
            .where(
                AlertModel.tenant_id == tenant_id,
                AlertModel.branch_id == branch_id,
                AlertModel.status.in_(OPEN_ALERT_STATUSES),
            )
            .order_by(AlertModel.fired_at.desc())
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_alert(row) for row in rows]

    async def get_open(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, rule_key: str, subject_ref: str
    ) -> Alert | None:
        stmt = select(AlertModel).where(
            AlertModel.tenant_id == tenant_id,
            AlertModel.branch_id == branch_id,
            AlertModel.rule_key == rule_key,
            AlertModel.subject_ref == subject_ref,
            AlertModel.status.in_(OPEN_ALERT_STATUSES),
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_alert(row) if row else None

    async def acknowledge(
        self,
        tenant_id: uuid.UUID,
        alert_id: uuid.UUID,
        employee_id: uuid.UUID,
        at: datetime,
    ) -> Alert | None:
        stmt = (
            update(AlertModel)
            .where(
                AlertModel.id == alert_id,
                AlertModel.tenant_id == tenant_id,
                # Condicional: quien la tome segundo toca cero filas y se entera.
                AlertModel.status == ALERT_FIRED,
            )
            .values(
                status=ALERT_ACKNOWLEDGED,
                acknowledged_at=at,
                acknowledged_by=employee_id,
            )
        )
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        await self._session.commit()
        if result.rowcount == 0:
            return None
        return await self.get_by_id(tenant_id, alert_id)

    async def resolve(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime
    ) -> Alert | None:
        stmt = (
            update(AlertModel)
            .where(
                AlertModel.id == alert_id,
                AlertModel.tenant_id == tenant_id,
                AlertModel.status.in_(OPEN_ALERT_STATUSES),
            )
            .values(status=ALERT_RESOLVED, resolved_at=at)
        )
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        await self._session.commit()
        if result.rowcount == 0:
            return None
        return await self.get_by_id(tenant_id, alert_id)

    def _open_with_rule(self) -> Any:
        """Alertas en `fired` con su regla encendida. El candidato de recordar y de escalar.

        `fired` y no `is_open`: tomarla es exactamente lo que corta las dos cosas.
        """
        return (
            select(AlertModel, AlertRuleModel)
            .join(
                AlertRuleModel,
                (AlertRuleModel.tenant_id == AlertModel.tenant_id)
                & (AlertRuleModel.branch_id == AlertModel.branch_id)
                & (AlertRuleModel.rule_key == AlertModel.rule_key),
            )
            .where(
                AlertModel.status == ALERT_FIRED,
                AlertRuleModel.is_enabled.is_(True),
            )
        )

    async def list_pending_escalation(
        self, now: datetime
    ) -> list[tuple[Alert, AlertRule]]:
        """Lo que toca escalar: la primera vez pasado el plazo, y luego cada 4 horas.

        Silenciar corta también el escalado: es una de las tres salidas, no sólo un botón del
        panel. Quien dice "ya lo sé" no necesita que se lo manden al teléfono.
        """
        stmt = self._open_with_rule().where(AlertModel.reminders_muted_at.is_(None))
        rows = (await self._session.execute(stmt)).all()
        pending: list[tuple[Alert, AlertRule]] = []
        for alert_row, rule_row in rows:
            alert = _to_alert(alert_row)
            rule = _to_rule(rule_row)
            # El plazo se compara en Python y no en SQL: `INTERVAL` a partir de una columna
            # no es portable entre Postgres y el SQLite de los tests, y el conjunto candidato
            # (alertas abiertas sin tomar) es pequeño por construcción.
            if alert.last_escalated_at is None:
                fired = alert.fired_at
                if fired is None:
                    continue
                due = rule.escalation_after_minutes * 60
                elapsed = (now - _as_utc(fired)).total_seconds()
            else:
                # Ya salió una vez: a partir de aquí manda el reloj del CANAL, no el de la
                # regla. Es lo que acota los mensajes de ese número a 6 al día.
                due = WHATSAPP_REESCALATION_HOURS * 3600
                elapsed = (now - _as_utc(alert.last_escalated_at)).total_seconds()
            if elapsed >= due:
                pending.append((alert, rule))
        return pending

    async def claim_escalation(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime, not_since: datetime
    ) -> bool:
        """Reclama el derecho a escalar. `True` sólo para el que toca la fila.

        `not_since` es el corte: sólo gana quien encuentra la alerta sin escalar desde antes de
        ese instante. Dos barridos solapados no pueden mandar el mismo WhatsApp dos veces, y
        reclamar ANTES de enviar hace que un envío fallido se pierda en vez de reintentarse en
        cada pasada — que es la fábrica de ruido que este módulo existe para no ser.
        """
        stmt = (
            update(AlertModel)
            .where(
                AlertModel.id == alert_id,
                AlertModel.tenant_id == tenant_id,
                AlertModel.status == ALERT_FIRED,
                AlertModel.reminders_muted_at.is_(None),
                sa_or(
                    AlertModel.last_escalated_at.is_(None),
                    AlertModel.last_escalated_at <= not_since,
                ),
            )
            .values(last_escalated_at=at)
        )
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        await self._session.commit()
        return bool(result.rowcount)

    # --- Recordatorios del panel --------------------------------------------
    async def list_pending_reminders(
        self, now: datetime
    ) -> list[tuple[Alert, AlertRule]]:
        """Lo que toca recordar: abierta, sin tomar, sin silenciar y con su intervalo cumplido.

        Una regla con `remind_every_minutes = 0` no entra: es la vía de escape que reproduce el
        comportamiento anterior a este change.

        `last_notified_at` en `NULL` cuenta como **debida**. Son las alertas que ya existían al
        desplegar esto, y llevan horas calladas: recordarlas de inmediato es lo correcto.
        """
        stmt = self._open_with_rule().where(
            AlertModel.reminders_muted_at.is_(None),
            AlertRuleModel.remind_every_minutes > 0,
        )
        rows = (await self._session.execute(stmt)).all()
        due: list[tuple[Alert, AlertRule]] = []
        for alert_row, rule_row in rows:
            alert = _to_alert(alert_row)
            rule = _to_rule(rule_row)
            if alert.last_notified_at is None:
                due.append((alert, rule))
                continue
            elapsed = (now - _as_utc(alert.last_notified_at)).total_seconds()
            if elapsed >= rule.remind_every_minutes * 60:
                due.append((alert, rule))
        return due

    async def claim_reminder(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime, not_since: datetime
    ) -> bool:
        """Reclama el derecho a recordar. Misma forma que `claim_escalation`, misma razón.

        Cuarta aparición de la misma idea en el proyecto —disparar, tomar, escalar y esto—,
        mantenida igual a propósito.
        """
        stmt = (
            update(AlertModel)
            .where(
                AlertModel.id == alert_id,
                AlertModel.tenant_id == tenant_id,
                AlertModel.status == ALERT_FIRED,
                AlertModel.reminders_muted_at.is_(None),
                sa_or(
                    AlertModel.last_notified_at.is_(None),
                    AlertModel.last_notified_at <= not_since,
                ),
            )
            .values(last_notified_at=at)
        )
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        await self._session.commit()
        return bool(result.rowcount)

    async def mute_reminders(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, at: datetime
    ) -> Alert | None:
        """La tercera salida. **No toca `status` ni `acknowledged_by`.**

        Silenciar no es tomar, y ésa es toda la diferencia: tomar afirma que alguien se hace
        cargo y el panel lo enseña; silenciar no afirma nada sobre nadie. Si callar exigiera
        tomar, el registro de quién atiende qué se llenaría de mentiras en una semana.

        Se silencia sólo lo abierto: una alerta ya resuelta no tiene recordatorios que callar.
        """
        stmt = (
            update(AlertModel)
            .where(
                AlertModel.id == alert_id,
                AlertModel.tenant_id == tenant_id,
                AlertModel.status.in_(OPEN_ALERT_STATUSES),
                AlertModel.reminders_muted_at.is_(None),
            )
            .values(reminders_muted_at=at)
        )
        await self._session.execute(stmt)
        await self._session.commit()
        # Se devuelve la alerta aunque no se haya tocado nada: silenciar dos veces es idempotente
        # y quien pulsa el botón otra vez merece ver el estado, no un error.
        return await self.get_by_id(tenant_id, alert_id)

    async def employee_name(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> str | None:
        # `select_from(EmployeeModel)` es estructural: seleccionando sólo columnas de
        # Person/User, SQLAlchemy adivina el FROM y acaba cruzando `employees` entero.
        stmt = (
            select(PersonModel.first_name, PersonModel.last_name, UserModel.email)
            .select_from(EmployeeModel)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            .join(PersonModel, PersonModel.id == EmployeeModel.person_id)
            .where(
                EmployeeModel.id == employee_id,
                EmployeeModel.tenant_id == tenant_id,
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        first_name, last_name, email = row
        full = " ".join(part for part in (first_name, last_name) if part).strip()
        return full or email

    async def employee_id_for_user(
        self, tenant_id: uuid.UUID, user_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Quién es esta persona EN ESTA SUCURSAL.

        Tomar una alerta se atribuye a un empleado, no a un usuario: es el mismo vocabulario
        que usa el inbox compartido para decir quién tiene una conversación.
        """
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.tenant_id == tenant_id,
            EmployeeModel.user_id == user_id,
            EmployeeModel.branch_id == branch_id,
            EmployeeModel.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, tenant_id: uuid.UUID, alert_id: uuid.UUID) -> Alert | None:
        stmt = select(AlertModel).where(
            AlertModel.id == alert_id, AlertModel.tenant_id == tenant_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _to_alert(row) if row else None
