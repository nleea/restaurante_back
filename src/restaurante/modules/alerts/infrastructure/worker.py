"""El proceso que vigila y el que publica a su hora. Segundo worker del sistema.

    poetry run arq restaurante.modules.alerts.infrastructure.worker.WorkerSettings

**EJECUTA EXACTAMENTE UNO.** No uno por host ni uno por réplica del API: uno. Y ahora hay DOS
motivos, de gravedad muy distinta — el segundo llegó con los estados de WhatsApp y es el que
importa antes de escalar este Deployment:

1. **Alertas: trabajo duplicado.** Dos procesos barriendo evalúan las mismas reglas en paralelo.
   Eso NO produce alertas duplicadas —el índice único parcial lo impide— pero sí trabajo de más
   y carreras al escalar que `mark_escalated` tiene que absorber en cada pasada.
2. **Estados: PUBLICACIONES duplicadas.** Dos procesos publicando la misma franja sacarían el
   mismo estado dos veces al teléfono de cada contacto. Lo que de verdad lo impide es el reclamo
   de emisión en la base (`try_claim_emission`, una fila por estado/fecha/minuto), igual que el
   índice del punto 1. Pero el daño de que ese reclamo fallara no es trabajo de más: es volumen
   de salida duplicado sobre un puente no oficial, que es lo que hace que baneen el número — y si
   el número cae, cae el canal entero.

`unique=True` en los crones lo evita dentro de un proceso y **no puede evitarlo entre dos**, y por
eso "cuántos workers" es un requisito escrito aquí y no un ajuste en un fichero.

Tres crones/caminos, y la diferencia entre los dos primeros es todo el diseño de las alertas:

- `evaluate_subject` — un job, anunciado tras un movimiento de stock. Es la LATENCIA: la
  alerta llega en segundos en vez de en el próximo barrido. Puede perderse, y no pasa nada.
- `sweep_alert_rules` — una pasada por TODAS las reglas encendidas de TODOS los tenants. Es
  la GARANTÍA, y es autoritativa: **quita el camino del job entero y el sistema sigue siendo
  correcto**, sólo que más lento. Encuentra lo que el job no encontró — Redis caído, el job
  murió, un camino de código que se olvidó de anunciar.
- `sweep_due_statuses` — publica los estados cuya franja venció. **Cron puro: no tiene camino de
  job, y no es un olvido.** Un horario es intrínsecamente temporal, así que no hay ningún hecho
  que anunciar; se cae la mitad complicada del patrón anterior y queda sólo la parte autoritativa.

Vive aquí y no en un worker propio por tres razones, en orden de peso: este proceso ya habla
WhatsApp (`whatsapp_escalation` importa el bridge y el guard, así que no se abre ninguna dirección
de acoplamiento nueva); su invariante de "exactamente uno" es literalmente lo que necesita un
programador de tareas; y un tercer worker cuesta tercera cola, tercer Deployment y tercer par
`manual-config`/`manual-secret` en k8s, todo para un cron.

El worker corre sin contexto de tenant y por eso ve los de todos. Es lo que necesita un
vigilante; ver sólo "los activos recientemente" es exactamente cómo se pierde la sucursal que
lleva dos días muda. Los estados lo necesitan por lo mismo, y por eso
`list_active_statuses_everywhere` existe con ese nombre.
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
from restaurante.modules.messaging.application.use_cases.statuses import StatusService
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.modules.messaging.infrastructure.whatsapp.bridge import (
    BridgeWhatsAppGateway,
)
from restaurante.modules.messaging.infrastructure.whatsapp.guard import (
    GuardedWhatsAppGateway,
)
from restaurante.shared.config import get_settings
from restaurante.shared.database import SessionFactory
from restaurante.shared.realtime.deps import get_event_publisher

_log = logging.getLogger(__name__)

#: El nombre del job. Se declara aquí, del lado que lo ejecuta, y el anunciante lo importa —
#: así los dos lados no pueden separarse en un job encolado para siempre que nadie corre.
EVALUATE_SUBJECT_JOB = "evaluate_alert_subject"

#: Cola propia, no la compartida de arq. Los dos workers apuntan al mismo Redis y arq encola
#: los CRON como cualquier otro job: en una sola cola, el worker de domicilios saca
#: `sweep_alert_rules`, no encuentra la función, escribe `function not found` y lo TIRA. El
#: barrido de ese ciclo no ocurre y la única huella queda en el log del OTRO worker. Con colas
#: separadas, cada uno sólo ve trabajo que sabe ejecutar.
ALERTS_QUEUE = "arq:queue:alerts"

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


def _build_statuses(session: Any) -> StatusService:
    """El servicio de estados sobre una sesión. Mismo cableado que el API, a propósito.

    Siempre el gateway GUARDADO, nunca el bridge a pelo: aunque un estado no pueda iniciar una
    conversación (no aterriza en ningún chat), el guard es también donde vive la comprobación de que
    el puente esté configurado y contactable, y eso tiene que ser lo mismo para los tres verbos.
    """
    settings = get_settings()
    repo = SqlAlchemyMessagingRepository(session)
    bridge = BridgeWhatsAppGateway(
        base_url=settings.whatsapp_bridge_base_url,
        api_key=settings.whatsapp_bridge_api_key,
        timeout_seconds=settings.whatsapp_bridge_timeout_seconds,
    )
    return StatusService(
        repo,
        GuardedWhatsAppGateway(bridge, repo),
        recipient_cap=settings.whatsapp_status_recipient_cap,
        inactivity_days=settings.whatsapp_status_inactivity_days,
        grace_minutes=settings.whatsapp_status_grace_minutes,
    )


async def sweep_due_statuses(ctx: dict[Any, Any]) -> str:
    """Publica los estados de WhatsApp cuya franja venció. Cron puro, sin camino de job.

    A diferencia de las alertas, aquí NO hay vía rápida ni anuncio por Redis, y no es un olvido: un
    horario es intrínsecamente temporal, así que no hay ningún hecho que anunciar. Se cae la mitad
    complicada del patrón y queda sólo el barrido, que ya era la parte autoritativa.
    """
    async with SessionFactory() as session:
        outcome = await _build_statuses(session).sweep()
    if outcome.published or outcome.failed or outcome.skipped_late or outcome.skipped_empty:
        _log.info(
            "Estados: %s considerados, %s publicados, %s fallidos, %s tarde, %s sin audiencia, "
            "%s ya hechos",
            outcome.statuses_considered,
            outcome.published,
            outcome.failed,
            outcome.skipped_late,
            outcome.skipped_empty,
            outcome.already_done,
        )
    return (
        f"considered={outcome.statuses_considered} published={outcome.published} "
        f"failed={outcome.failed} late={outcome.skipped_late} "
        f"empty={outcome.skipped_empty} done={outcome.already_done}"
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
        ),
        cron(
            sweep_due_statuses,
            # CADA minuto, no cada cinco: una franja se programa a una hora concreta y el dueño
            # espera que salga a esa hora. La ventana de gracia absorbe el retraso de un proceso
            # caído, no el de un cron perezoso.
            minute=set(range(0, 60)),
            second=10,
            # Aquí `unique` importa MÁS que arriba: dos pasadas solapadas en alertas duplican
            # trabajo, y en estados duplicarían PUBLICACIONES. Lo que de verdad lo impide es el
            # reclamo de emisión en la base; esto es la primera de las dos defensas.
            unique=True,
        ),
    ]

    # Sólo los jobs de este worker — ver ALERTS_QUEUE. Tiene que coincidir con el pool del
    # anunciante, o los anuncios caen en una cola que nadie lee.
    queue_name = ALERTS_QUEUE

    # A diferencia del worker de domicilios, aquí no hay límite externo que respetar: las
    # evaluaciones son consultas a nuestra propia base. Se deja bajo igualmente para que una
    # tanda de movimientos de stock no compita con el barrido por el pool de conexiones.
    max_jobs = 4

    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
