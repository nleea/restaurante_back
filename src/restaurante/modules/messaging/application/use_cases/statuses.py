"""Componer, programar y publicar estados de WhatsApp.

Es la primera emisión del módulo que no es una respuesta, y todo lo raro de este fichero sale de esa
única frase. Lo que hay que saber antes de tocarlo:

**Validar al GUARDAR, nunca al publicar.** Un estado de texto sin `bg_color` o sin `font` es un 400
del proveedor. Si eso se descubre al publicar, se descubre a las once de la mañana, dentro de un
worker, sin nadie mirando: el dueño se entera por un teléfono vacío. Así que se rechaza al guardar,
que es el mismo criterio que ya usan los marcadores de `templates.py`.

**El barrido es lo único que hay, y es autoritativo.** No hay camino de job ni anuncio por Redis: un
horario es intrínsecamente temporal, no hay nada que anunciar. Quítale cualquier otra cosa y sigue
siendo correcto.

**No publicar también deja fila.** `skipped_late` y `skipped_empty` existen porque un estado que no
sale tiene que ser algo que el dueño pueda leer, no un silencio. Es lo que hace defendible la
ventana de gracia: si el worker estuvo caído desde las once, sacar el menú del día a las tres de la
tarde es peor que no sacarlo — pero callarse es peor que las dos cosas.

**Una publicación es UNA llamada.** No se trocea la audiencia aquí. Evolution la parte en tandas de
diez y las reenvía con el mismo `messageId`, que es lo que hace que el espectador vea una sola
historia; trocear por nuestra cuenta convertiría 200 destinatarios en 20 historias idénticas. La
pausa que sí ponemos es **entre estados distintos** del mismo barrido.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from dataclasses import dataclass
from datetime import date

from restaurante.modules.business.application.clock import now_local
from restaurante.modules.messaging.domain.entities import (
    StatusPublication,
    WhatsAppStatus,
)
from restaurante.modules.messaging.domain.errors import MessageDeliveryError
from restaurante.modules.messaging.domain.ports import (
    MessagingRepository,
    WhatsAppGateway,
)
from restaurante.modules.messaging.domain.status_audience import (
    StatusAudience,
    resolve_audience,
)
from restaurante.modules.messaging.domain.status_schedule import (
    DueSlot,
    StatusSlot,
    due_slots,
    emission_detail,
    validate_slots,
)
from restaurante.modules.messaging.infrastructure.models import (
    EMISSION_STATUS_POST,
    PUBLICATION_FAILED,
    PUBLICATION_PUBLISHED,
    PUBLICATION_SKIPPED_EMPTY,
    PUBLICATION_SKIPPED_LATE,
    STATUS_TYPE_IMAGE,
    STATUS_TYPE_TEXT,
    STATUS_TYPES,
)
from restaurante.shared.domain.errors import NotFoundError, ValidationError

logger = logging.getLogger(__name__)

#: Pausa entre la publicación de un estado y la del siguiente, dentro del mismo barrido.
#:
#: No es entre tandas —eso lo hace el puente— sino entre PUBLICACIONES. Dos estados que vencen el
#: mismo minuto son dos ráfagas de veinte llamadas cada una: seguidas y sin pausa son una firma.
#: El rango es irregular a propósito; un intervalo fijo también es una firma.
JITTER_SECONDS = (1.5, 4.0)


@dataclass(frozen=True)
class SweepOutcome:
    """Lo que hizo una pasada. Entero, porque un barrido silencioso no se puede auditar."""

    statuses_considered: int = 0
    published: int = 0
    failed: int = 0
    skipped_late: int = 0
    skipped_empty: int = 0
    already_done: int = 0


def validate_composition(
    status_type: str,
    *,
    content: str,
    bg_color: str | None,
    font: int | None,
) -> None:
    """Rechaza al guardar lo que el proveedor rechazaría al publicar.

    Los dos campos de la tarjeta no son decoración: `formatStatusMessage` de Evolution devuelve 400
    sin ellos. Es la razón entera de que un estado se "componga" en vez de escribirse.
    """
    if status_type not in STATUS_TYPES:
        raise ValidationError(f"Tipo de estado desconocido: {status_type}.")
    if not content.strip():
        raise ValidationError("Un estado necesita contenido.")
    if status_type == STATUS_TYPE_TEXT:
        if not bg_color:
            raise ValidationError(
                "Un estado de texto necesita color de fondo: WhatsApp lo exige."
            )
        if font is None:
            raise ValidationError(
                "Un estado de texto necesita una fuente: WhatsApp la exige."
            )


class StatusService:
    """Los estados de una sede, y el barrido que los publica.

    El barrido no recibe sede ni tenant: los ve todos, como el de alertas y por el mismo motivo. Ver
    `list_active_statuses_everywhere`.
    """

    def __init__(
        self,
        repository: MessagingRepository,
        gateway: WhatsAppGateway,
        *,
        recipient_cap: int,
        inactivity_days: int,
        grace_minutes: int,
    ) -> None:
        # Se construye igual desde el API y desde el worker, y los dos inyectan el gateway
        # GUARDADO — no el bridge a pelo. Es el único sitio por donde sale algo hacia WhatsApp.
        self._repo = repository
        self._gateway = gateway
        self._cap = recipient_cap
        self._inactivity_days = inactivity_days
        self._grace_minutes = grace_minutes

    # --- Lectura y escritura de la pantalla ---------------------------------
    async def list_statuses(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[WhatsAppStatus]:
        return await self._repo.list_statuses(tenant_id, branch_id)

    async def get_status(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, status_id: uuid.UUID
    ) -> WhatsAppStatus:
        status = await self._repo.get_status(tenant_id, branch_id, status_id)
        if status is None:
            raise NotFoundError("El estado no existe.")
        return status

    async def create_status(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status_type: str,
        content: str,
        slots: list[StatusSlot],
        bg_color: str | None = None,
        font: int | None = None,
        caption: str | None = None,
        media_url: str | None = None,
        created_by: uuid.UUID | None = None,
    ) -> WhatsAppStatus:
        validate_composition(
            status_type, content=content, bg_color=bg_color, font=font
        )
        validate_slots(slots)
        status_id = await self._repo.create_status(
            tenant_id,
            branch_id,
            status_type=status_type,
            content=content,
            bg_color=bg_color if status_type == STATUS_TYPE_TEXT else None,
            font=font if status_type == STATUS_TYPE_TEXT else None,
            caption=caption if status_type == STATUS_TYPE_IMAGE else None,
            media_url=media_url if status_type == STATUS_TYPE_IMAGE else None,
            created_by=created_by,
        )
        await self._repo.replace_slots(tenant_id, branch_id, status_id, slots)
        return await self.get_status(tenant_id, branch_id, status_id)

    async def update_status(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        status_id: uuid.UUID,
        *,
        status_type: str,
        content: str,
        slots: list[StatusSlot],
        bg_color: str | None = None,
        font: int | None = None,
        caption: str | None = None,
        media_url: str | None = None,
        active: bool = True,
    ) -> WhatsAppStatus:
        await self.get_status(tenant_id, branch_id, status_id)
        validate_composition(
            status_type, content=content, bg_color=bg_color, font=font
        )
        validate_slots(slots)
        await self._repo.update_status(
            tenant_id,
            branch_id,
            status_id,
            type=status_type,
            content=content,
            bg_color=bg_color if status_type == STATUS_TYPE_TEXT else None,
            font=font if status_type == STATUS_TYPE_TEXT else None,
            caption=caption if status_type == STATUS_TYPE_IMAGE else None,
            media_url=media_url if status_type == STATUS_TYPE_IMAGE else None,
            active=active,
        )
        # Borrar y reinsertar, como `operating_hours`. Ver `replace_slots`.
        await self._repo.replace_slots(tenant_id, branch_id, status_id, slots)
        return await self.get_status(tenant_id, branch_id, status_id)

    async def delete_status(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, status_id: uuid.UUID
    ) -> None:
        deleted = await self._repo.delete_status(tenant_id, branch_id, status_id)
        if not deleted:
            raise NotFoundError("El estado no existe.")

    async def preview_audience(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> StatusAudience:
        """La audiencia y sus cuatro bajas, para enseñarlas ANTES de programar nada.

        Es la misma resolución que usa el barrido, a propósito: si la previa y la publicación
        calcularan la audiencia distinto, la pantalla estaría prometiendo un número que no ocurre.
        """
        return await self._resolve(tenant_id, branch_id)

    async def list_publications(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, status_id: uuid.UUID
    ) -> list[StatusPublication]:
        await self.get_status(tenant_id, branch_id, status_id)
        return await self._repo.list_publications(tenant_id, branch_id, status_id)

    # --- El barrido ---------------------------------------------------------
    async def sweep(self) -> SweepOutcome:
        """Una pasada por TODOS los estados encendidos de TODOS los tenants.

        La hora sale de `clock.now_local()` y de ahí se descompone en fecha local y minuto. Nunca
        `datetime.now(UTC)`: a partir de las 19:00 en Colombia el día de la semana ya está corrido
        en
        UTC, así que un barrido en UTC publicaría el horario de mañana. Es el fallo que hizo nacer
        `clock.py`.
        """
        moment = now_local()
        local_date = moment.date()
        now_minute = moment.hour * 60 + moment.minute

        statuses = await self._repo.list_active_statuses_everywhere()
        outcome = SweepOutcome(statuses_considered=len(statuses))
        published = failed = late = empty = already = 0
        first = True

        for status in statuses:
            for due in due_slots(
                status.slots, local_date, now_minute, self._grace_minutes
            ):
                if not first:
                    # Entre PUBLICACIONES, no entre tandas. Dos estados que vencen el mismo minuto
                    # son dos ráfagas de veinte llamadas; seguidas y sin pausa son una firma.
                    await asyncio.sleep(random.uniform(*JITTER_SECONDS))
                first = False

                state = await self._publish_one(status, due, local_date)
                if state is None:
                    already += 1
                elif state == PUBLICATION_PUBLISHED:
                    published += 1
                elif state == PUBLICATION_FAILED:
                    failed += 1
                elif state == PUBLICATION_SKIPPED_LATE:
                    late += 1
                else:
                    empty += 1

        return SweepOutcome(
            statuses_considered=outcome.statuses_considered,
            published=published,
            failed=failed,
            skipped_late=late,
            skipped_empty=empty,
            already_done=already,
        )

    async def _publish_one(
        self, status: WhatsAppStatus, due: DueSlot, local_date: date
    ) -> str | None:
        """Publica una franja vencida. `None` si otro ya la reclamó.

        El reclamo va PRIMERO, antes de resolver la audiencia y antes de mirar la gracia: es lo que
        hace que dos barridos en el mismo minuto publiquen una vez, y lo que hace que un
        `skipped_late` no se reconsidere en cada pasada durante el resto del día.
        """
        claimed = await self._repo.try_claim_emission(
            status.tenant_id,
            status.branch_id,
            kind=EMISSION_STATUS_POST,
            detail=emission_detail(status.id, local_date, due.minute),
        )
        if not claimed:
            return None

        if not due.within_grace:
            # No se publica, pero se registra: un estado caduca a las 24 horas, así que sacar el
            # menú
            # del día por la tarde es peor que no sacarlo — y callarse es peor que las dos cosas.
            await self._record(
                status, due, local_date, PUBLICATION_SKIPPED_LATE
            )
            logger.info(
                "Estado omitido por llegar tarde: %s (%s min de retraso)",
                status.id,
                due.late_by,
            )
            return PUBLICATION_SKIPPED_LATE

        audience = await self._resolve(status.tenant_id, status.branch_id)
        if audience.is_empty:
            await self._record(
                status, due, local_date, PUBLICATION_SKIPPED_EMPTY, audience
            )
            return PUBLICATION_SKIPPED_EMPTY

        session = await self._repo.get_session_for_branch(
            status.tenant_id, status.branch_id
        )
        if session is None:
            await self._record(
                status, due, local_date, PUBLICATION_FAILED, audience
            )
            logger.warning(
                "Estado sin número emparejado en la sede: %s", status.branch_id
            )
            return PUBLICATION_FAILED

        try:
            provider_id = await self._gateway.publish_status(
                session,
                audience.jids,
                status_type=status.type,
                content=status.content,
                bg_color=status.bg_color,
                font=status.font,
                caption=status.caption,
            )
        except MessageDeliveryError as exc:
            logger.warning("El puente rechazó el estado %s: %s", status.id, exc)
            await self._record(status, due, local_date, PUBLICATION_FAILED, audience)
            return PUBLICATION_FAILED

        await self._record(
            status,
            due,
            local_date,
            PUBLICATION_PUBLISHED,
            audience,
            provider_message_id=provider_id,
        )
        return PUBLICATION_PUBLISHED

    async def _resolve(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> StatusAudience:
        candidates = await self._repo.list_status_candidates(tenant_id, branch_id)
        return resolve_audience(
            candidates,
            now=now_local(),
            inactivity_days=self._inactivity_days,
            configured_cap=self._cap,
        )

    async def _record(
        self,
        status: WhatsAppStatus,
        due: DueSlot,
        local_date: date,
        state: str,
        audience: StatusAudience | None = None,
        *,
        provider_message_id: str | None = None,
    ) -> None:
        """La fila de constancia. `addressed_count` es "a cuántos se dirigió".

        Nunca "a cuántos llegó": el proveedor no devuelve vistas y devuelve 201 aunque se le caigan
        tandas. Las cuatro exclusiones van por separado y no sumadas, porque un total no puede decir
        *por qué* la audiencia bajó de 340 a 200 — y `excluded_by_cap > 0` es lo único que distingue
        "llegó a todos los que podía" de "esto se truncó".
        """
        await self._repo.record_publication(
            status.tenant_id,
            status.branch_id,
            status.id,
            fired_for_date=local_date,
            minute=due.minute,
            state=state,
            addressed_count=audience.addressed_count if audience else 0,
            excluded_no_number=audience.excluded_no_number if audience else 0,
            excluded_opted_out=audience.excluded_opted_out if audience else 0,
            excluded_inactive=audience.excluded_inactive if audience else 0,
            excluded_by_cap=audience.excluded_by_cap if audience else 0,
            late_by_minutes=due.late_by,
            provider_message_id=provider_message_id,
        )
