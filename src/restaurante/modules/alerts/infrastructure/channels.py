"""El canal de tiempo real. El de WhatsApp vive en `whatsapp_escalation.py`.

Están separados porque tienen dependencias muy distintas: este sólo necesita el publicador
compartido, y el otro conoce messaging entero. Meterlos en un fichero haría que importar el
timbre arrastrase el puente de WhatsApp.

El orden entre ellos tampoco es casual: el tiempo real cuesta cero, llega al instante y no
puede hacer que bloqueen un número de teléfono. WhatsApp se gasta únicamente en una alerta
que nadie tomó en el plazo configurado — es decir, en algo genuinamente ignorado.

*Se consideró* mandar WhatsApp de inmediato en las reglas "críticas". Se descartó: qué regla
es crítica es un juicio para el que nadie tiene datos todavía, y el plazo de escalado expresa
la misma intención sin inventar un segundo concepto.

Ninguno de los dos lo importa el dominio: se inyectan desde la raíz de composición, así que
`alert-notifications` funciona con WhatsApp completamente ausente.
"""

from __future__ import annotations

import logging

from restaurante.modules.alerts.domain.entities import Alert
from restaurante.modules.alerts.domain.ports import Subject
from restaurante.shared.realtime.ports import EventPublisher

logger = logging.getLogger(__name__)

#: Topic del timbre. La pantalla de alertas escucha aquí y refresca; el payload es grueso a
#: propósito —dice QUE algo cambió, no cuál es el estado nuevo.
ALERTS_TOPIC = "alerts"


class RealtimeNotificationChannel:
    """El timbre en la aplicación. Best-effort: `publish` no levanta por contrato."""

    def __init__(self, publisher: EventPublisher) -> None:
        self._publisher = publisher

    async def notify(self, alert: Alert, subject: Subject, kind: str) -> None:
        await self._publisher.publish(
            ALERTS_TOPIC,
            alert.tenant_id,
            alert.branch_id,
            {
                "kind": kind,
                "rule_key": alert.rule_key,
                "subject": subject.label,
                "detail": subject.detail,
            },
        )
