"""El proceso que vigila. Segundo worker del sistema.

    poetry run arq restaurante.modules.alerts.infrastructure.worker.WorkerSettings

**EJECUTA EXACTAMENTE UNO.** No uno por host ni uno por réplica del API: uno. El motivo no es
el de domicilios —allí es un límite de la API de geocodificación— sino el barrido: dos
procesos barriendo a la vez evalúan las mismas reglas en paralelo. Eso NO produce alertas
duplicadas, porque el índice único parcial lo impide; produce trabajo duplicado y, sobre todo,
carreras al escalar que `mark_escalated` tiene que absorber en cada pasada. `unique=True` en el
cron lo evita dentro de un proceso y no puede evitarlo entre dos, y por eso "cuántos workers"
es un requisito escrito aquí y no un ajuste en un fichero.

Dos caminos, y la diferencia es todo el diseño:

- `evaluate_subject` — un job, anunciado tras un movimiento de stock. Es la LATENCIA: la
  alerta llega en segundos en vez de en el próximo barrido. Puede perderse, y no pasa nada.
- `sweep_alert_rules` — una pasada por TODAS las reglas encendidas de TODOS los tenants. Es
  la GARANTÍA, y es autoritativa: **quita el camino del job entero y el sistema sigue siendo
  correcto**, sólo que más lento. Encuentra lo que el job no encontró — Redis caído, el job
  murió, un camino de código que se olvidó de anunciar.

El worker corre sin contexto de tenant y por eso ve los de todos. Es lo que necesita un
vigilante; ver sólo "los activos recientemente" es exactamente cómo se pierde la sucursal que
lleva dos días muda.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from arq import cron, func
from arq.connections import RedisSettings

# Registra todos los modelos en Base.metadata (claves foráneas entre módulos).
import restaurante.shared.models_registry  # noqa: F401
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
from restaurante.modules.alerts.infrastructure.whatsapp_escalation import (
    WhatsAppEscalationChannel,
)
from restaurante.shared.config import get_settings
from restaurante.shared.database import SessionFactory
from restaurante.shared.realtime.deps import get_event_publisher

_log = logging.getLogger(__name__)

#: El nombre del job. Se declara aquí, del lado que lo ejecuta, y el anunciante lo importa —
#: así los dos lados no pueden separarse en un job encolado para siempre que nadie corre.
EVALUATE_SUBJECT_JOB = "evaluate_alert_subject"

#: Cada cuántos minutos barre. Cinco es la conjetura de partida: el stock bajo no necesita
#: segundos. Una sucursal muda discutiblemente sí, y por eso esto acabará siendo por regla.
SWEEP_MINUTE_STEP = 5


def _build(session: Any) -> AlertSweeper:
    """El evaluador completo sobre una sesión. Mismo cableado que el API, a propósito.

    Si el worker y el API construyeran las reglas distinto, el barrido dejaría de ser
    autoritativo sin que nadie se enterara: evaluaría otra cosa.
    """
    repo = SqlAlchemyAlertRepository(session)
    registry = build_registry(
        inventory=SqlAlchemyInventoryReader(session),
        sessions=SqlAlchemySessionReader(session),
        cash=SqlAlchemyCashReader(session),
        assistant=SqlAlchemyAssistantQuotaReader(session),
    )
    evaluators: dict[str, AlertRuleEvaluator] = dict(registry)  # type: ignore[arg-type]
    lifecycle = AlertLifecycle(
        repo,
        channels=[RealtimeNotificationChannel(get_event_publisher())],
        # El escalado a WhatsApp SÓLO vive aquí, en el worker. El API no lo tiene: una
        # petición HTTP —alguien pulsando "tomar", abriendo el panel— nunca debe poder
        # provocar un envío a nadie. Escalar es una consecuencia del tiempo que pasa, no de
        # que alguien mire la pantalla.
        escalation_channels=[WhatsAppEscalationChannel(session)],
    )
    return AlertSweeper(repo, lifecycle, evaluators)


async def evaluate_alert_subject(
    ctx: dict[Any, Any],
    tenant_id: str,
    branch_id: str,
    rule_key: str,
    subject_ref: str,
) -> str:
    """Evalúa UN sujeto de UNA regla. El camino rápido.

    Los identificadores viajan como texto porque un job serializado no debe depender de que
    el codificador de arq sepa de `UUID`.
    """
    async with SessionFactory() as session:
        outcome = await _build(session).evaluate_subject(
            uuid.UUID(tenant_id), uuid.UUID(branch_id), rule_key, subject_ref
        )
    return f"fired={outcome.fired} resolved={outcome.resolved}"


async def sweep_alert_rules(ctx: dict[Any, Any]) -> str:
    """La pasada autoritativa. Correcta con el camino del job eliminado por completo."""
    async with SessionFactory() as session:
        outcome = await _build(session).sweep()
    _log.info(
        "Barrido de alertas: %s reglas, %s disparadas, %s resueltas, %s recordadas, "
        "%s escaladas",
        outcome.rules_evaluated,
        outcome.fired,
        outcome.resolved,
        outcome.reminded,
        outcome.escalated,
    )
    return (
        f"rules={outcome.rules_evaluated} fired={outcome.fired} "
        f"resolved={outcome.resolved} reminded={outcome.reminded} "
        f"escalated={outcome.escalated}"
    )


class WorkerSettings:
    """El worker de alertas. `arq <la ruta de esta clase>`. Uno solo — ver el módulo."""

    functions = [func(evaluate_alert_subject, name=EVALUATE_SUBJECT_JOB)]
    cron_jobs = [
        cron(
            sweep_alert_rules,
            minute=set(range(0, 60, SWEEP_MINUTE_STEP)),
            second=0,
            # Por defecto de arq, dicho en voz alta porque importa: impide que el barrido se
            # solape consigo mismo DENTRO de este proceso. Entre dos procesos no puede.
            unique=True,
        )
    ]

    # A diferencia del worker de domicilios, aquí no hay límite externo que respetar: las
    # evaluaciones son consultas a nuestra propia base. Se deja bajo igualmente para que una
    # tanda de movimientos de stock no compita con el barrido por el pool de conexiones.
    max_jobs = 4

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
