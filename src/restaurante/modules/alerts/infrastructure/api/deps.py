"""Raíz de composición del módulo de alertas.

Aquí se decide lo que el diseño prometió: el canal de tiempo real va SIEMPRE, y el de
WhatsApp sólo si el puente existe. Alertas no importa messaging en ninguna otra parte del
módulo — el adaptador se le entrega hecho, así que quitar WhatsApp del despliegue no rompe
nada y la regla de sesión caída simplemente deja de estar registrada.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.alerts.application.use_cases.evaluators import build_registry
from restaurante.modules.alerts.application.use_cases.lifecycle import AlertLifecycle
from restaurante.modules.alerts.application.use_cases.sweep import AlertSweeper
from restaurante.modules.alerts.domain.ports import AlertRuleEvaluator
from restaurante.modules.alerts.infrastructure.channels import (
    RealtimeNotificationChannel,
)
from restaurante.modules.alerts.infrastructure.readers import (
    SqlAlchemyAssistantQuotaReader,
    SqlAlchemyCashReader,
    SqlAlchemyInventoryReader,
    SqlAlchemySessionReader,
)
from restaurante.modules.alerts.infrastructure.repositories import (
    SqlAlchemyAlertRepository,
)
from restaurante.shared.api.deps import get_tenant_id
from restaurante.shared.database import get_session
from restaurante.shared.realtime.deps import get_event_publisher

SessionDep = Annotated[AsyncSession, Depends(get_session)]
TenantDep = Annotated[uuid.UUID, Depends(get_tenant_id)]


def build_lifecycle(session: AsyncSession) -> AlertLifecycle:
    """El ciclo de vida con el tiempo real enchufado.

    Sin canal de escalado: escalar por WhatsApp es cosa del worker, no de una petición HTTP.
    Un usuario pulsando "tomar" no debe poder disparar un envío a nadie.
    """
    return AlertLifecycle(
        SqlAlchemyAlertRepository(session),
        channels=[RealtimeNotificationChannel(get_event_publisher())],
    )


def build_sweeper(session: AsyncSession) -> AlertSweeper:
    """El evaluador completo: reglas + lectores + ciclo de vida."""
    repo = SqlAlchemyAlertRepository(session)
    registry = build_registry(
        inventory=SqlAlchemyInventoryReader(session),
        sessions=SqlAlchemySessionReader(session),
        cash=SqlAlchemyCashReader(session),
        assistant=SqlAlchemyAssistantQuotaReader(session),
    )
    evaluators: dict[str, AlertRuleEvaluator] = {
        key: value  # type: ignore[misc]
        for key, value in registry.items()
    }
    return AlertSweeper(repo, build_lifecycle(session), evaluators)


def get_lifecycle(session: SessionDep) -> AlertLifecycle:
    return build_lifecycle(session)


def get_repository(session: SessionDep) -> SqlAlchemyAlertRepository:
    return SqlAlchemyAlertRepository(session)


LifecycleDep = Annotated[AlertLifecycle, Depends(get_lifecycle)]
RepositoryDep = Annotated[SqlAlchemyAlertRepository, Depends(get_repository)]
