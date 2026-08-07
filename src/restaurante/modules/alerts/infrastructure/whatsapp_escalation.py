"""Escalar a WhatsApp: el aviso al personal cuando nadie tomó la alerta.

Es el **primer envío automático de este sistema a alguien que no es un cliente**, y por eso
está acotado por cuatro cosas a la vez, no por una:

1. **El plazo.** Sólo se escala lo que lleva sin tomar más de `escalation_after_minutes`.
2. **Que alguien la tome.** Tomarla es exactamente lo que lo cancela.
3. **Que la regla lo tenga encendido.** `escalate_to_whatsapp` es una decisión por regla.
4. **El guardián del canal.** Se escribe con el gateway GUARDADO, que rechaza escribir a
   quien no escribió primero. Así que sólo llega a empleados que ya son contactos del
   negocio; a quien no lo sea no le llega nada. Eso no es un fallo, es la propiedad: el
   sistema nunca inicia una conversación de WhatsApp, ni siquiera con su propia gente.

Y el escalado **se anota igual aunque no salga**. Un envío que falla no puede reintentarse
en cada barrido: la alerta seguiría sin tomar y le escribiría al mismo número cada cinco
minutos, que es la fábrica de ruido que este módulo entero existe para no ser.

Sobre la dependencia: este fichero SÍ conoce messaging, y es el único de `alerts` que puede.
Es un adaptador de infraestructura implementando un puerto del dominio — la flecha sigue
saliendo. El dominio y la aplicación de alertas no lo importan; la raíz de composición lo
enchufa, y si no lo enchufa el módulo funciona igual, sólo que sin escalar.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.alerts.domain.entities import Alert
from restaurante.modules.alerts.domain.ports import Subject
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.messaging.infrastructure.models import WhatsAppContactModel
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.modules.messaging.infrastructure.whatsapp.bridge import (
    BridgeWhatsAppGateway,
)
from restaurante.modules.messaging.infrastructure.whatsapp.guard import (
    GuardedWhatsAppGateway,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.config import get_settings

logger = logging.getLogger(__name__)

#: Quién PUEDE recibir el escalado. No basta con tenerlo: hace falta además que la persona
#: esté suscrita (`employees.receives_alerts`).
#:
#: Se pide el permiso porque un aviso a alguien que después no puede abrir la pantalla es un
#: aviso inútil; y se pide la suscripción porque el permiso solo mezclaba dos cosas distintas
#: —ver el panel y que le escriban de noche— sin forma de separarlas.
ESCALATION_PERMISSION = "alerts.read"


@dataclass(frozen=True)
class EscalationReach:
    """Qué pasaría si una alerta escalara ahora. Es un diagnóstico, no una estadística.

    Los cuatro campos existen para separar cuatro causas distintas de "no llegó nada", que
    desde la pantalla son indistinguibles entre sí y de "está roto".
    """

    #: La sucursal tiene número y está conectado. Sin esto, nada más importa.
    has_session: bool
    #: Cuántos han sido señalados para recibirlo (y pueden ver alertas).
    subscribed: int
    #: De los señalados, cuántos tienen un chat de WhatsApp emparejado.
    with_chat: int
    #: De esos, a cuántos se les puede escribir de verdad (ya escribieron al número).
    reachable: int


@dataclass(frozen=True)
class Recipient:
    """Una persona señalada, y a qué chat se le escribiría."""

    employee_id: uuid.UUID
    name: str
    #: La dirección del chat emparejado: un número o un `@lid`. Vacía = sin emparejar, y
    #: entonces no se le puede escribir por mucho que tenga teléfono en su ficha.
    address: str


class WhatsAppEscalationChannel:
    """Implementa `NotificationChannel` sobre el canal de WhatsApp de la sucursal."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._messaging = SqlAlchemyMessagingRepository(session)
        self._rbac = SqlAlchemyRbacRepository(session)

    async def reach(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> EscalationReach:
        """A cuánta gente llegaría un escalado AHORA MISMO, y por qué a los demás no.

        Existe porque "no llegó nada" es indistinguible de "está apagado" desde la pantalla.
        Los tres números separan las tres causas: sin teléfono, sin permiso, o —la más
        confusa— con todo bien pero sin haber escrito nunca al número del negocio, que es lo
        que el guardián exige y nadie adivina.
        """
        session = await self._messaging.get_session_for_branch(tenant_id, branch_id)
        candidates = await self._candidates(tenant_id, branch_id)
        linked = [c for c in candidates if c.address]
        reachable = 0
        for candidate in linked:
            if await self._messaging.is_reachable(tenant_id, candidate.address):
                reachable += 1
        return EscalationReach(
            has_session=session is not None and session.status == "connected",
            subscribed=len(candidates),
            with_chat=len(linked),
            reachable=reachable,
        )

    async def roster(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[tuple[Recipient, bool]]:
        """Los señalados, con si se les puede escribir. Para explicarlo persona a persona."""
        out: list[tuple[Recipient, bool]] = []
        for candidate in await self._candidates(tenant_id, branch_id):
            reachable = bool(candidate.address) and await self._messaging.is_reachable(
                tenant_id, candidate.address
            )
            out.append((candidate, reachable))
        return out

    async def notify(self, alert: Alert, subject: Subject, kind: str) -> None:
        """Escribe a quien pueda atender esto. Nunca levanta; puede no enviar a nadie."""
        wa_session = await self._messaging.get_session_for_branch(
            alert.tenant_id, alert.branch_id
        )
        if wa_session is None:
            # La sucursal no tiene número vinculado. No es un error: es un negocio que no
            # usa WhatsApp, y el aviso ya salió por tiempo real.
            logger.info(
                "Alerta %s sin escalar: la sucursal %s no tiene número vinculado.",
                alert.id,
                alert.branch_id,
            )
            return

        recipients = await self._recipients(alert.tenant_id, alert.branch_id)
        if not recipients:
            logger.info(
                "Alerta %s sin escalar: nadie señalado con chat emparejado en %s (%s).",
                alert.id,
                ESCALATION_PERMISSION,
                alert.branch_id,
            )
            return

        text = _compose(subject)
        gateway = self._build_gateway()
        for recipient in recipients:
            try:
                await gateway.send_text(wa_session, recipient.address, text)
            except Exception:  # noqa: BLE001
                # Lo normal aquí es el rechazo del guardián: ese empleado nunca escribió al
                # número del negocio, así que no se le puede escribir. Es información, no un
                # fallo, y no puede impedir que se avise a los demás.
                logger.info(
                    "No se pudo escalar la alerta %s a %s.",
                    alert.id,
                    recipient.name,
                    exc_info=True,
                )

    # --- Destinatarios ------------------------------------------------------
    async def _recipients(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[Recipient]:
        """A quién se le escribe: los señalados que además tienen chat emparejado."""
        return [c for c in await self._candidates(tenant_id, branch_id) if c.address]

    async def _candidates(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[Recipient]:
        """Los señalados para recibir el aviso, tengan teléfono o no.

        Tres condiciones y ninguna sobra: activo en ESTA sucursal, **suscrito** (alguien lo
        eligió), y con el permiso EFECTIVO (roles ∪ allow − deny) — la misma definición que
        usa el guardián de los endpoints, para que no pueda haber alguien que reciba el aviso
        y luego no pueda abrir la pantalla.

        Sin chat emparejado se devuelven igual: el diagnóstico necesita poder decir "hay dos
        señalados pero ninguno tiene chat", que es una causa distinta de "no hay nadie
        señalado" y se arregla en otro sitio.
        """
        stmt = (
            select(
                EmployeeModel.id,
                EmployeeModel.user_id,
                PersonModel.first_name,
                PersonModel.last_name,
                WhatsAppContactModel.phone,
            )
            .select_from(EmployeeModel)
            .join(PersonModel, PersonModel.id == EmployeeModel.person_id)
            .join(UserModel, UserModel.id == EmployeeModel.user_id)
            # LEFT JOIN: quien no tiene chat emparejado sigue contando como señalado, para
            # que el diagnóstico pueda distinguir esa causa de las demás.
            .join(
                WhatsAppContactModel,
                WhatsAppContactModel.id == EmployeeModel.whatsapp_contact_id,
                isouter=True,
            )
            .where(
                EmployeeModel.tenant_id == tenant_id,
                EmployeeModel.branch_id == branch_id,
                EmployeeModel.is_active.is_(True),
                EmployeeModel.receives_alerts.is_(True),
                UserModel.is_active.is_(True),
            )
        )
        rows = (await self._session.execute(stmt)).all()

        recipients: list[Recipient] = []
        for employee_id, user_id, first, last, address in rows:
            codes = await self._rbac.effective_permission_codes(tenant_id, user_id)
            if ESCALATION_PERMISSION not in codes:
                continue
            name = " ".join(part for part in (first, last) if part).strip()
            recipients.append(
                Recipient(
                    employee_id=employee_id, name=name or "—", address=str(address or "")
                )
            )
        return recipients

    def _build_gateway(self) -> GuardedWhatsAppGateway:
        """SIEMPRE el guardado. Un aviso al personal tampoco puede iniciar una conversación."""
        settings = get_settings()
        bridge = BridgeWhatsAppGateway(
            base_url=settings.whatsapp_bridge_base_url,
            api_key=settings.whatsapp_bridge_api_key,
            timeout_seconds=settings.whatsapp_bridge_timeout_seconds,
        )
        return GuardedWhatsAppGateway(bridge, self._messaging)


def _compose(subject: Subject) -> str:
    """El texto del escalado.

    Dice qué pasa, desde cuándo lleva pasando implícitamente (nadie la tomó) y a dónde ir.
    No trae botones ni pide respuesta: contestar por WhatsApp no toma la alerta, y sugerirlo
    sería prometer algo que no existe.
    """
    detail = f"\n{subject.detail}" if subject.detail else ""
    return (
        f"⚠️ *{subject.label}*{detail}\n\n"
        "Nadie ha tomado esta alerta. Míralo en la aplicación."
    )
