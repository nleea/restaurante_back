"""El barrido que publica, y las cuatro propiedades de la clave de emisión.

Estas cuatro son el change entero, y todas se rompen del mismo modo si la clave se toca:

- dos barridos en el mismo minuto publican UNA vez,
- guardar el estado a las 11:05 NO republica el de las 11:00,
- dos franjas del mismo día publican dos veces,
- la misma franja publica otra vez al día siguiente.

El reloj se sustituye porque el barrido pregunta la hora y no se le puede pasar: es lo único que no
se puede probar con una función pura, y es exactamente donde vivía el fallo de `clock.py`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
import pytest_asyncio
from httpx import AsyncClient

from restaurante.modules.messaging.application.use_cases import statuses as sut
from restaurante.modules.messaging.application.use_cases.statuses import StatusService
from restaurante.modules.messaging.domain.entities import WhatsAppSession
from restaurante.modules.messaging.domain.errors import MessageDeliveryError
from restaurante.modules.messaging.domain.status_schedule import StatusSlot
from restaurante.modules.messaging.infrastructure.models import (
    PUBLICATION_FAILED,
    PUBLICATION_PUBLISHED,
    PUBLICATION_SKIPPED_EMPTY,
    PUBLICATION_SKIPPED_LATE,
)
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.shared.database import SessionFactory

from .conftest import create_branch, create_session_row, demo_tenant_id, post_inbound

BOGOTA = ZoneInfo("America/Bogota")
ELEVEN = 11 * 60
SIX_THIRTY = 18 * 60 + 30
MONDAY = date(2026, 8, 10)


class RecordingGateway:
    """Un gateway que apunta lo que le piden publicar. Nunca toca la red."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self._fail = fail

    async def publish_status(
        self,
        session: WhatsAppSession,
        jids: list[str],
        *,
        status_type: str,
        content: str,
        bg_color: str | None = None,
        font: int | None = None,
        caption: str | None = None,
    ) -> str | None:
        if self._fail:
            raise MessageDeliveryError("el puente dijo no")
        self.calls.append(
            {"jids": list(jids), "type": status_type, "content": content}
        )
        return f"st-{len(self.calls)}"


def _at(day: date, minute: int) -> datetime:
    return datetime(
        day.year, day.month, day.day, minute // 60, minute % 60, tzinfo=BOGOTA
    )


@pytest.fixture(autouse=True)
def _no_jitter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin pausa entre publicaciones: en producción protege el número, aquí sólo alarga la suite."""
    monkeypatch.setattr(sut, "JITTER_SECONDS", (0.0, 0.0))


def _freeze(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(sut, "now_local", lambda: moment)


async def _service(gateway: RecordingGateway) -> tuple[StatusService, Any]:
    session = SessionFactory()
    repo = SqlAlchemyMessagingRepository(session)
    return (
        StatusService(
            repo,
            gateway,  # type: ignore[arg-type]
            recipient_cap=200,
            inactivity_days=90,
            grace_minutes=30,
        ),
        session,
    )


@pytest_asyncio.fixture
async def branch_with_audience(client: AsyncClient) -> dict[str, Any]:
    """Una sede con número emparejado y un contacto que escribió (así hay audiencia)."""
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    await post_inbound(client, "inst-centro", message_id="a1", phone="+573001112233")
    return {"branch_id": branch_id, "tenant_id": await demo_tenant_id()}


async def _create(
    ctx: dict[str, Any], slots: list[StatusSlot], content: str = "Hoy hay sancocho"
) -> uuid.UUID:
    gateway = RecordingGateway()
    service, session = await _service(gateway)
    async with session:
        created = await service.create_status(
            ctx["tenant_id"],
            ctx["branch_id"],
            status_type="text",
            content=content,
            slots=slots,
            bg_color="#0B3D2E",
            font=2,
        )
    return created.id


async def _sweep(
    monkeypatch: pytest.MonkeyPatch, moment: datetime, gateway: RecordingGateway
) -> Any:
    _freeze(monkeypatch, moment)
    service, session = await _service(gateway)
    async with session:
        return await service.sweep()


async def _publications(ctx: dict[str, Any], status_id: uuid.UUID) -> list[Any]:
    async with SessionFactory() as session:
        repo = SqlAlchemyMessagingRepository(session)
        return await repo.list_publications(
            ctx["tenant_id"], ctx["branch_id"], status_id
        )


# --- Las cuatro propiedades de la clave -------------------------------------
@pytest.mark.asyncio
async def test_two_sweeps_in_the_same_minute_publish_once(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)
    second = await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)

    assert len(gateway.calls) == 1
    assert second.already_done == 1
    assert len(await _publications(ctx, status_id)) == 1


@pytest.mark.asyncio
async def test_saving_the_status_again_does_not_republish_it(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La razón entera de que la clave no lleve el id de la franja.

    Guardar reescribe las filas de franjas con UUIDs nuevos. Con el id dentro de la clave, corregir
    una tilde a las 11:05 haría que el barrido de las 11:06 no encontrara la emisión y publicara
    otra vez — y el dueño no tendría forma de relacionar una cosa con la otra.
    """
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)

    # El dueño corrige el texto a las 11:05. Las franjas se borran y se reinsertan.
    service, session = await _service(gateway)
    async with session:
        await service.update_status(
            ctx["tenant_id"],
            ctx["branch_id"],
            status_id,
            status_type="text",
            content="Hoy hay sancocho de gallina",
            slots=[StatusSlot(minute=ELEVEN, weekday=0)],
            bg_color="#0B3D2E",
            font=2,
        )

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN + 6), gateway)

    assert len(gateway.calls) == 1, "un guardado inocuo republicó el estado"
    assert len(await _publications(ctx, status_id)) == 1


@pytest.mark.asyncio
async def test_two_slots_on_the_same_day_publish_twice(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = branch_with_audience
    status_id = await _create(
        ctx,
        [StatusSlot(minute=ELEVEN, weekday=0), StatusSlot(minute=SIX_THIRTY, weekday=0)],
    )
    gateway = RecordingGateway()

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)
    await _sweep(monkeypatch, _at(MONDAY, SIX_THIRTY), gateway)

    assert len(gateway.calls) == 2
    minutes = sorted(p.minute for p in await _publications(ctx, status_id))
    assert minutes == [ELEVEN, SIX_THIRTY]


@pytest.mark.asyncio
async def test_the_same_slot_publishes_again_the_next_week(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """La fecha local está en la clave, y es lo que hace que un estado semanal vuelva a salir."""
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)
    await _sweep(monkeypatch, _at(MONDAY + timedelta(days=7), ELEVEN), gateway)

    assert len(gateway.calls) == 2
    dates = sorted(p.fired_for_date for p in await _publications(ctx, status_id))
    assert dates == [MONDAY, MONDAY + timedelta(days=7)]


# --- La ventana de gracia ---------------------------------------------------
@pytest.mark.asyncio
async def test_a_late_slot_is_recorded_as_skipped_not_published(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """No publicar deja FILA. Es lo que hace defendible la ventana de gracia."""
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    outcome = await _sweep(monkeypatch, _at(MONDAY, ELEVEN + 160), gateway)

    assert gateway.calls == []
    assert outcome.skipped_late == 1
    published = await _publications(ctx, status_id)
    assert [p.state for p in published] == [PUBLICATION_SKIPPED_LATE]
    assert published[0].late_by_minutes == 160


@pytest.mark.asyncio
async def test_a_late_slot_is_not_reconsidered_on_the_next_sweep(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """El omitido reclama la emisión igual, o el barrido lo reevalúa cada minuto todo el día."""
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN + 160), gateway)
    await _sweep(monkeypatch, _at(MONDAY, ELEVEN + 161), gateway)

    assert len(await _publications(ctx, status_id)) == 1


@pytest.mark.asyncio
async def test_a_slot_inside_the_grace_window_still_publishes(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN + 29), gateway)

    assert len(gateway.calls) == 1
    assert [p.state for p in await _publications(ctx, status_id)] == [
        PUBLICATION_PUBLISHED
    ]


# --- El día de la semana en hora local -------------------------------------
@pytest.mark.asyncio
async def test_an_evening_slot_publishes_on_its_local_weekday(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    """A las 20:00 en Bogotá ya es el martes en UTC.

    La franja del lunes tiene que salir el LUNES. Es el fallo de `clock.py` aplicado a publicar.
    """
    ctx = branch_with_audience
    await _create(ctx, [StatusSlot(minute=20 * 60, weekday=0)])
    gateway = RecordingGateway()

    moment = _at(MONDAY, 20 * 60)
    assert moment.astimezone(ZoneInfo("UTC")).date() == date(2026, 8, 11)

    await _sweep(monkeypatch, moment, gateway)

    assert len(gateway.calls) == 1


# --- Los otros dos finales -------------------------------------------------
@pytest.mark.asyncio
async def test_a_bridge_rejection_is_recorded_as_failed(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])

    outcome = await _sweep(
        monkeypatch, _at(MONDAY, ELEVEN), RecordingGateway(fail=True)
    )

    assert outcome.failed == 1
    assert [p.state for p in await _publications(ctx, status_id)] == [
        PUBLICATION_FAILED
    ]


@pytest.mark.asyncio
async def test_an_empty_audience_is_its_own_outcome(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sin nadie a quien publicar no es `failed` (nada se rompió) ni `published` (no salió).

    Y la fila trae las cuatro exclusiones, que son exactamente la explicación de por qué no había
    nadie — que es la única cosa útil que se le puede decir al dueño en ese momento.
    """
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    ctx = {"branch_id": branch_id, "tenant_id": await demo_tenant_id()}
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    outcome = await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)

    assert gateway.calls == []
    assert outcome.skipped_empty == 1
    assert [p.state for p in await _publications(ctx, status_id)] == [
        PUBLICATION_SKIPPED_EMPTY
    ]


@pytest.mark.asyncio
async def test_the_audience_that_reaches_the_bridge_is_a_full_jid(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = branch_with_audience
    await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)

    assert gateway.calls[0]["jids"] == ["573001112233@s.whatsapp.net"]


@pytest.mark.asyncio
async def test_an_inactive_status_never_publishes(
    branch_with_audience: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    ctx = branch_with_audience
    status_id = await _create(ctx, [StatusSlot(minute=ELEVEN, weekday=0)])
    gateway = RecordingGateway()

    service, session = await _service(gateway)
    async with session:
        await service.update_status(
            ctx["tenant_id"],
            ctx["branch_id"],
            status_id,
            status_type="text",
            content="Hoy hay sancocho",
            slots=[StatusSlot(minute=ELEVEN, weekday=0)],
            bg_color="#0B3D2E",
            font=2,
            active=False,
        )

    await _sweep(monkeypatch, _at(MONDAY, ELEVEN), gateway)

    assert gateway.calls == []
