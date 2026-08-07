"""El ciclo de vida de una alerta: disparar, recordar, tomar, silenciar, resolver, escalar.

Lo difícil de este módulo no es detectar. Es **insistir sin convertirse en ruido**.

Este fichero decía lo contrario —"preferimos un aviso perdido a cuarenta repetidos"— y esa
frase era buena como advertencia y equivocada como diseño. Puesta en producción produjo lo
previsible: un aviso, a una hora en la que nadie miraba la pantalla, y silencio durante un día
entero con la condición encendida todo el tiempo. **Avisar una vez es avisar a quien estuviera
mirando en ese segundo.**

Lo que hacía insoportable repetir no era repetir: era que sólo se podía parar tomando la alerta
—o sea mintiendo, "me hago cargo"— o esperando a que la condición desapareciera sola. Faltaba
poder decir "ya lo sé". Con esa tercera salida, repetir deja de ser ruido y pasa a ser
insistencia, que es lo que un aviso operativo tiene que ser.

Cuatro reglas lo sostienen, y ninguna es un `if`:

1. **Disparar es reclamar.** `claim_fire` inserta contra un índice único parcial sobre las
   alertas abiertas. Quien inserta, avisa; quien choca, calla. El job y el barrido pueden
   mirar el mismo sujeto a la vez y sale un solo aviso.
2. **La histéresis es obligatoria y asimétrica.** Se dispara en el umbral y sólo se re-arma
   pasado `umbral + colchón`. Un colchón de cero es exactamente el fallo que esto existe
   para evitar, así que el dominio lo rechaza — no la UI.
3. **Insistir cuesta un toque callarlo.** Tres salidas, y las tres cortan tanto los
   recordatorios del panel como los mensajes de WhatsApp: tomarla, resolverla, silenciarla.
   Quitar cualquiera devuelve el módulo a la máquina de ruido que la advertencia describía.
4. **Cada canal insiste a su ritmo, y el caro no lo decide la regla.** El panel repite cada
   `remind_every_minutes` porque cuesta cero; WhatsApp manda el primero al cumplirse el plazo de
   la regla y luego uno cada 4 horas —techo de 6 al día—, y ese ritmo es una constante del
   módulo: quien paga un mensaje de más no es el dueño, es el número.

Un canal caído sigue sin perder la alerta: cuando se notifica, ya está guardada. Se pierde el
aviso, no el hecho, y ahora además llega el siguiente recordatorio.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta

from restaurante.modules.alerts.domain.entities import (
    WHATSAPP_REESCALATION_HOURS,
    Alert,
    AlertRule,
)
from restaurante.modules.alerts.domain.errors import AlreadyAcknowledgedError
from restaurante.modules.alerts.domain.ports import (
    AlertRepository,
    NotificationChannel,
    Subject,
)
from restaurante.shared.domain.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

# Tipos de aviso. El canal decide qué hacer con cada uno; el ciclo de vida sólo los nombra.
NOTIFY_FIRED = "fired"
# Un recordatorio con el mismo texto que el primero se lee como un problema NUEVO, y a la tercera
# vez el panel parece estar contando cuatro alertas donde hay una.
NOTIFY_REMINDER = "reminder"
NOTIFY_ESCALATED = "escalated"


class AlertLifecycle:
    def __init__(
        self,
        repo: AlertRepository,
        channels: list[NotificationChannel] | None = None,
        escalation_channels: list[NotificationChannel] | None = None,
    ) -> None:
        self._repo = repo
        # Siempre presentes (tiempo real). Cuestan cero y no pueden hacer que bloqueen un
        # número de teléfono.
        self._channels = channels or []
        # Sólo para escalar. Puede estar vacío: el módulo funciona con WhatsApp ausente.
        self._escalation = escalation_channels or []

    # --- Disparo ------------------------------------------------------------
    async def fire(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject: Subject,
    ) -> Alert | None:
        """Dispara si nadie lo había hecho ya. `None` cuando otro ganó la carrera.

        Sólo el ganador avisa. Es lo que hace que el job y el barrido evaluando el mismo
        sujeto produzcan una alerta y un aviso, no dos.
        """
        alert = await self._repo.claim_fire(
            tenant_id, branch_id, rule_key, subject.ref, subject.label
        )
        if alert is None:
            return None
        # El disparo CUENTA como aviso: sin esto el primer recordatorio saldría en el barrido
        # siguiente —cinco minutos después del primer aviso, sí, pero por accidente— en vez de
        # un intervalo completo después.
        now = datetime.now(UTC)
        if alert.id is not None:
            await self._repo.claim_reminder(tenant_id, alert.id, now, now)
        await self._notify(self._channels, alert, subject, NOTIFY_FIRED)
        return alert

    # --- Toma ---------------------------------------------------------------
    async def acknowledge(
        self, tenant_id: uuid.UUID, alert_id: uuid.UUID, employee_id: uuid.UUID
    ) -> Alert:
        """Anota quién la tomó. Perder la carrera dice quién la tiene, no "error"."""
        alert = await self._repo.acknowledge(
            tenant_id, alert_id, employee_id, datetime.now(UTC)
        )
        if alert is not None:
            return alert
        # Cero filas: o no existe, o ya la tomó alguien. Son cosas distintas y se dicen
        # distinto — "no existe" manda a mirar otra pantalla, "la tiene Ana" no.
        existing = await self._repo.get_by_id(tenant_id, alert_id)
        if existing is None:
            raise NotFoundError("La alerta no existe.")
        holder = (
            await self._repo.employee_name(tenant_id, existing.acknowledged_by)
            if existing.acknowledged_by
            else None
        )
        raise AlreadyAcknowledgedError(holder)

    # --- Resolución ---------------------------------------------------------
    async def resolve_cleared(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject_refs: list[str],
    ) -> int:
        """Cierra las alertas de los sujetos que se recuperaron **pasado el colchón**.

        Quien decide qué está recuperado es el evaluador de la regla, no esto: la histéresis
        vive donde se conoce la unidad (kilos, minutos, estado de una sesión). Aquí sólo se
        cierra lo que ya se declaró limpio.

        Cerrar es lo que vuelve a armar el sujeto. Sin esto una alerta se queda abierta para
        siempre y ese sujeto no puede volver a avisar nunca — silencio permanente y sin
        síntoma, que es peor que el ruido.
        """
        now = datetime.now(UTC)
        closed = 0
        for ref in subject_refs:
            alert = await self._repo.get_open(tenant_id, branch_id, rule_key, ref)
            if alert is None or alert.id is None:
                continue
            if await self._repo.resolve(tenant_id, alert.id, now) is not None:
                closed += 1
        return closed

    # --- Recordatorios del panel --------------------------------------------
    async def remind_pending(self, subjects: dict[str, Subject] | None = None) -> int:
        """Vuelve a avisar por el PANEL de lo que sigue abierto y sin tocar.

        **Sólo `self._channels`, nunca `self._escalation`.** Un recordatorio no puede provocar
        un mensaje de WhatsApp: el panel cuesta cero y puede insistir cada cinco minutos, y el
        teléfono no. Los dos canales insisten, pero con relojes distintos y el de WhatsApp lo
        lleva `escalate_pending`.

        Que esto exista es lo que arregla el defecto de fondo del módulo: avisar una vez es
        avisar a quien estuviera mirando en ese segundo.
        """
        now = datetime.now(UTC)
        reminded = 0
        for alert, rule in await self._repo.list_pending_reminders(now):
            if alert.id is None:
                continue
            # Reclamar ANTES de avisar, igual que el disparo, la toma y el escalado. Un canal
            # lento no puede producir recordatorios duplicados, que es lo que la gente odia.
            not_since = now - timedelta(minutes=rule.remind_every_minutes)
            if not await self._repo.claim_reminder(
                alert.tenant_id, alert.id, now, not_since
            ):
                continue
            await self._notify(
                self._channels, alert, self._subject_of(alert, subjects), NOTIFY_REMINDER
            )
            reminded += 1
        return reminded

    async def mute_reminders(self, tenant_id: uuid.UUID, alert_id: uuid.UUID) -> Alert:
        """La tercera salida: "ya lo sé, cállate".

        No la toma ni la cierra — la alerta sigue abierta, sin dueño y visible en el panel.
        Existe porque sin ella la única forma de callar un aviso sería tomarlo, o sea afirmar
        que alguien se hace cargo cuando no es verdad; y ese registro es lo único que hace útil
        el panel.
        """
        alert = await self._repo.mute_reminders(tenant_id, alert_id, datetime.now(UTC))
        if alert is None:
            raise NotFoundError("La alerta no existe.")
        return alert

    def _subject_of(
        self, alert: Alert, subjects: dict[str, Subject] | None
    ) -> Subject:
        """Cómo se llama el sujeto, con la mejor fuente disponible. El orden importa:

        1. el sujeto VIVO que acaba de calcular el barrido — trae el detalle al día;
        2. el nombre congelado al disparar — sin detalle, pero dice "Azúcar";
        3. la referencia cruda, que es fea pero identifica.

        El detalle ("quedan 1.84 de 3") sólo viaja en el caso 1 a propósito: horas después
        sería un número viejo presentado como actual.
        """
        return (subjects or {}).get(alert.subject_ref) or Subject(
            ref=alert.subject_ref,
            label=alert.subject_label or alert.subject_ref,
        )

    # --- Escalado -----------------------------------------------------------
    async def escalate_pending(self, subjects: dict[str, Subject] | None = None) -> int:
        """Escala a WhatsApp: la primera vez pasado el plazo de la regla, y luego cada 4 horas.

        Dos relojes y no uno, y la diferencia es la que separa insistir de que bloqueen el
        número del negocio: el panel puede repetir cada cinco minutos porque no cuesta nada;
        aquí el techo son **6 mensajes al día** por alerta, y lo fija el canal, no la regla.

        Las tres salidas —tomarla, resolverla, silenciarla— cortan esto igual que cortan los
        recordatorios.
        """
        now = datetime.now(UTC)
        escalated = 0
        for alert, rule in await self._repo.list_pending_escalation(now):
            if alert.id is None or not rule.escalate_to_whatsapp:
                continue
            # Se marca ANTES de enviar. Un envío que falla no debe reintentarse en el
            # siguiente barrido: la alerta seguiría sin tomar y lo escalaría cada pasada,
            # que es la fábrica de ruido que este módulo existe para no ser.
            not_since = now - timedelta(hours=WHATSAPP_REESCALATION_HOURS)
            if not await self._repo.claim_escalation(
                alert.tenant_id, alert.id, now, not_since
            ):
                continue
            await self._notify(
                self._escalation,
                alert,
                self._subject_of(alert, subjects),
                NOTIFY_ESCALATED,
            )
            escalated += 1
        return escalated

    # --- Configuración ------------------------------------------------------
    async def save_rule(self, rule: AlertRule) -> AlertRule:
        """Guarda la configuración de una regla, rechazando un colchón de cero.

        Se valida aquí y no sólo en la pantalla porque un colchón de cero no es una
        preferencia de usuario: es el bug. Con cero, un valor oscilando en el umbral produce
        cuarenta alertas, alguien silencia el módulo, y la siguiente alerta de verdad no la
        ve nadie.
        """
        if rule.recovery_buffer <= 0:
            raise ValidationError(
                "El colchón de recuperación no puede ser cero: sin él, un valor que oscila "
                "en el umbral vuelve a avisar en cada evaluación."
            )
        if rule.escalation_after_minutes <= 0:
            raise ValidationError(
                "El plazo de escalado debe ser de al menos un minuto."
            )
        return await self._repo.save_rule(rule)

    # --- Envío --------------------------------------------------------------
    async def _notify(
        self,
        channels: list[NotificationChannel],
        alert: Alert,
        subject: Subject,
        kind: str,
    ) -> None:
        for channel in channels:
            try:
                await channel.notify(alert, subject, kind)
            except Exception:  # noqa: BLE001
                # La alerta ya está guardada. Un canal caído se lleva el aviso, nunca el
                # hecho, y nunca la mutación que lo disparó.
                logger.warning(
                    "No se pudo notificar la alerta %s por %s",
                    alert.id,
                    type(channel).__name__,
                    exc_info=True,
                )
