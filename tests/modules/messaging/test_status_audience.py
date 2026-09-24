"""La audiencia de un estado y sus cuatro reducciones.

Aquí está el riesgo del change, así que se prueba con datos y no a ojo. Dos pruebas son las que lo
sostienen:

- `test_the_full_reduction_table_from_the_design` es la tabla del diseño, fila por fila. Si se cae,
  el número de destinatarios ha dejado de ser el que el diseño defiende.
- `test_a_contact_of_another_branch_is_not_in_the_audience` es la asimetría con `is_reachable`, que
  es deliberadamente por negocio. Si se cae, publicamos a gente que no puede vernos.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy import update as sql_update

from restaurante.modules.messaging.domain.status_audience import (
    ABSOLUTE_RECIPIENT_CEILING,
    StatusCandidate,
    effective_cap,
    is_privacy_jid,
    publication_calls,
    resolve_audience,
    to_jid,
    with_own_jid,
)
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppContactModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.shared.database import SessionFactory

from .conftest import (
    create_branch,
    create_session_row,
    demo_tenant_id,
    post_inbound,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)


def _candidate(
    address: str, *, days_ago: int = 1, opted_out: bool = False
) -> StatusCandidate:
    return StatusCandidate(
        address=address,
        last_inbound_at=NOW - timedelta(days=days_ago),
        opted_out=opted_out,
    )


def _resolve(
    candidates: list[StatusCandidate], *, cap: int = 200, days: int = 90
):
    return resolve_audience(
        candidates, now=NOW, inactivity_days=days, configured_cap=cap
    )


# --- JIDs de privacidad ------------------------------------------------------
def test_a_privacy_jid_is_recognised() -> None:
    assert is_privacy_jid("123456@lid")
    assert not is_privacy_jid("573001112233")


def test_a_privacy_jid_is_excluded_and_counted() -> None:
    """Excluir visiblemente gana a incluir y fallar callado: el puente devuelve 201 igual."""
    audience = _resolve([_candidate("123456@lid"), _candidate("573001112233")])
    assert audience.jids == ["573001112233@s.whatsapp.net"]
    assert audience.excluded_no_number == 1


def test_an_ordinary_number_becomes_a_full_jid() -> None:
    assert to_jid("+57 300 111 2233") == "573001112233@s.whatsapp.net"


# --- Opt-out ----------------------------------------------------------------
def test_an_opted_out_contact_is_excluded_and_counted() -> None:
    audience = _resolve(
        [_candidate("573001112233", opted_out=True), _candidate("573002223344")]
    )
    assert audience.jids == ["573002223344@s.whatsapp.net"]
    assert audience.excluded_opted_out == 1


# --- Ventana de inactividad --------------------------------------------------
def test_an_inactive_contact_is_excluded_and_counted() -> None:
    audience = _resolve(
        [_candidate("573001112233", days_ago=91), _candidate("573002223344", days_ago=89)]
    )
    assert audience.jids == ["573002223344@s.whatsapp.net"]
    assert audience.excluded_inactive == 1


def test_the_window_edge_is_included() -> None:
    audience = _resolve([_candidate("573001112233", days_ago=90)])
    assert audience.addressed_count == 1


# --- El tope ----------------------------------------------------------------
def test_the_cap_bites_last_and_reports_what_it_dropped() -> None:
    candidates = [_candidate(f"5730011122{i:02d}") for i in range(10)]
    audience = _resolve(candidates, cap=4)
    assert audience.addressed_count == 4
    assert audience.excluded_by_cap == 6


def test_the_cap_keeps_the_most_recent_contacts() -> None:
    """El orden es lo que hace que el tope no sea un sorteo. Cortar una lista sin orden deja un
    subconjunto arbitrario, que es elegir al azar quién ve el menú del día."""
    candidates = [
        _candidate("573000000001", days_ago=1),
        _candidate("573000000002", days_ago=2),
        _candidate("573000000003", days_ago=3),
    ]
    audience = _resolve(candidates, cap=2)
    assert audience.jids == [
        "573000000001@s.whatsapp.net",
        "573000000002@s.whatsapp.net",
    ]


def test_the_configured_cap_cannot_exceed_the_domain_ceiling() -> None:
    """Un techo configurable no es un techo."""
    assert effective_cap(5000) == ABSOLUTE_RECIPIENT_CEILING
    assert effective_cap(200) == 200


def test_a_cap_above_the_ceiling_does_not_publish_beyond_it() -> None:
    candidates = [
        _candidate(f"57300{i:07d}") for i in range(ABSOLUTE_RECIPIENT_CEILING + 20)
    ]
    audience = _resolve(candidates, cap=10_000)
    assert audience.addressed_count == ABSOLUTE_RECIPIENT_CEILING
    assert audience.excluded_by_cap == 20


# --- La tabla del diseño ----------------------------------------------------
def test_the_full_reduction_table_from_the_design() -> None:
    """340 → 12 `@lid` → 4 opt-out → 118 inactivos → tope 200 → 6 omitidos.

    Los cinco números salen por separado, y suman con el total. Si se sumaran en uno, una lista
    itemizada que no cuadra no se puede leer — y un "publicado a 200" sobre 340 se lee como
    cobertura completa.
    """
    candidates = (
        [_candidate(f"{i}@lid") for i in range(12)]
        + [_candidate(f"5730100{i:04d}", opted_out=True) for i in range(4)]
        + [_candidate(f"5730200{i:04d}", days_ago=120) for i in range(118)]
        + [_candidate(f"5730300{i:04d}") for i in range(206)]
    )
    assert len(candidates) == 340

    audience = _resolve(candidates, cap=200)

    assert audience.total_candidates == 340
    assert audience.excluded_no_number == 12
    assert audience.excluded_opted_out == 4
    assert audience.excluded_inactive == 118
    assert audience.excluded_by_cap == 6
    assert audience.addressed_count == 200

    # Cuadra: cada contacto cae en exactamente un cubo.
    assert (
        audience.addressed_count
        + audience.excluded_no_number
        + audience.excluded_opted_out
        + audience.excluded_inactive
        + audience.excluded_by_cap
        == audience.total_candidates
    )


def test_a_contact_falls_in_exactly_one_bucket() -> None:
    """Un `@lid` que además pidió no recibir se cuenta UNA vez, en el primero que lo excluye."""
    audience = _resolve([_candidate("123@lid", opted_out=True, days_ago=200)])
    assert audience.excluded_no_number == 1
    assert audience.excluded_opted_out == 0
    assert audience.excluded_inactive == 0


def test_an_empty_audience_is_reported_as_empty() -> None:
    audience = _resolve([_candidate("1@lid"), _candidate("2@lid")])
    assert audience.is_empty
    assert audience.excluded_no_number == 2


# --- El coste de una publicación -------------------------------------------
def test_the_number_of_provider_calls_is_the_risk_number() -> None:
    """200 destinatarios son 20 llamadas a `status@broadcast`. Ese número es el riesgo."""
    assert publication_calls(200) == 20
    assert publication_calls(201) == 21
    assert publication_calls(0) == 0


def test_we_never_split_the_list_ourselves() -> None:
    """La propiedad que protege esta función documentando, y que el módulo debe respetar.

    Evolution parte en tandas de diez y las reenvía con el MISMO `messageId`, así que el espectador
    ve UNA historia. Partir nosotros haría de cada tanda una publicación con su propio id: 200
    destinatarios serían 20 historias idénticas. Por eso `publish_status` recibe la lista entera y
    en este módulo no existe ninguna función que la trocee.
    """
    import restaurante.modules.messaging.domain.status_audience as mod

    assert not hasattr(mod, "batched")


# --- La consulta, contra la base --------------------------------------------
@pytest_asyncio.fixture
async def two_branches(client: AsyncClient) -> dict[str, uuid.UUID]:
    """Dos sedes, cada una con su número emparejado."""
    centro = await create_branch("centro", primary=True)
    norte = await create_branch("norte")
    await create_session_row(centro, "inst-centro")
    await create_session_row(norte, "inst-norte")
    return {"centro": centro, "norte": norte}


async def _candidates_of(branch_id: uuid.UUID) -> list[StatusCandidate]:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        repo = SqlAlchemyMessagingRepository(session)
        return await repo.list_status_candidates(tenant_id, branch_id)


@pytest.mark.asyncio
async def test_a_contact_who_wrote_to_this_branch_is_a_candidate(
    client: AsyncClient, two_branches: dict[str, uuid.UUID]
) -> None:
    await post_inbound(client, "inst-centro", message_id="c1", phone="+573001112233")

    candidates = await _candidates_of(two_branches["centro"])
    assert [c.address for c in candidates] == ["573001112233"]
    assert candidates[0].opted_out is False


@pytest.mark.asyncio
async def test_a_contact_of_another_branch_is_not_in_the_audience(
    client: AsyncClient, two_branches: dict[str, uuid.UUID]
) -> None:
    """La asimetría con `is_reachable`, que es deliberadamente por NEGOCIO.

    Quien escribió al número del norte no tiene guardado el número del centro, así que su teléfono
    no le va a enseñar la historia del centro pase lo que pase. Incluirlo sería volumen de salida
    sin audiencia posible detrás — que es exactamente lo que puede costar la cuenta.
    """
    await post_inbound(client, "inst-norte", message_id="n1", phone="+573009998877")

    assert await _candidates_of(two_branches["centro"]) == []
    assert [c.address for c in await _candidates_of(two_branches["norte"])] == [
        "573009998877"
    ]


async def _set_inbound_at(phone: str, when: datetime) -> None:
    """Fija a mano el `sent_at` de los mensajes entrantes de un contacto.

    Hace falta porque el webhook deja `sent_at = now()` y en una prueba los tres mensajes caen en el
    mismo instante, así que el `MAX` empata y el orden es arbitrario. En producción llegan separados
    por segundos o minutos; el empate es artefacto de la prueba, no del código, y lo que se quiere
    comprobar aquí es precisamente que ordena por esa columna.
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        contact_id = (
            await session.execute(
                select(WhatsAppContactModel.id).where(
                    WhatsAppContactModel.tenant_id == tenant_id,
                    WhatsAppContactModel.phone == phone,
                )
            )
        ).scalar_one()
        conversation_ids = (
            (
                await session.execute(
                    select(WhatsAppConversationModel.id).where(
                        WhatsAppConversationModel.whatsapp_contact_id == contact_id
                    )
                )
            )
            .scalars()
            .all()
        )
        await session.execute(
            sql_update(WhatsAppMessageModel)
            .where(
                WhatsAppMessageModel.whatsapp_conversation_id.in_(conversation_ids),
                WhatsAppMessageModel.sender_type == "contact",
            )
            .values(sent_at=when)
        )
        await session.commit()


@pytest.mark.asyncio
async def test_candidates_come_ordered_by_most_recent_inbound(
    client: AsyncClient, two_branches: dict[str, uuid.UUID]
) -> None:
    """El orden es un requisito de la consulta, no una comodidad: es lo que hace que el tope
    conserve a los que escribieron hace menos."""
    await post_inbound(client, "inst-centro", message_id="a1", phone="+573000000001")
    await post_inbound(client, "inst-centro", message_id="b1", phone="+573000000002")
    await post_inbound(client, "inst-centro", message_id="c1", phone="+573000000003")

    await _set_inbound_at("573000000001", NOW - timedelta(days=3))
    await _set_inbound_at("573000000002", NOW - timedelta(days=1))
    await _set_inbound_at("573000000003", NOW - timedelta(days=2))

    candidates = await _candidates_of(two_branches["centro"])
    assert [c.address for c in candidates] == [
        "573000000002",
        "573000000003",
        "573000000001",
    ]

    # Y el tope, sobre ese orden, conserva a los dos más recientes.
    audience = _resolve(candidates, cap=2)
    assert audience.jids == [
        "573000000002@s.whatsapp.net",
        "573000000003@s.whatsapp.net",
    ]


@pytest.mark.asyncio
async def test_recency_ignores_our_own_replies(
    client: AsyncClient, two_branches: dict[str, uuid.UUID]
) -> None:
    """La recencia se mide sólo sobre ENTRANTES.

    Una respuesta que mandamos ayer no dice nada de si esa persona sigue ahí, y contarla mantendría
    "vivo" para siempre a cualquiera al que le hayamos escrito.
    """
    await post_inbound(client, "inst-centro", message_id="old", phone="+573001112233")
    await _set_inbound_at("573001112233", NOW - timedelta(days=200))

    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        conversation_id = (
            await session.execute(select(WhatsAppConversationModel.id))
        ).scalar_one()
        session.add(
            WhatsAppMessageModel(
                tenant_id=tenant_id,
                branch_id=two_branches["centro"],
                whatsapp_conversation_id=conversation_id,
                sender_type="employee",
                content="hola",
                delivery_state="sent",
                sent_at=NOW,
            )
        )
        await session.commit()

    candidates = await _candidates_of(two_branches["centro"])
    assert candidates[0].last_inbound_at == NOW - timedelta(days=200)
    assert _resolve(candidates).excluded_inactive == 1


@pytest.mark.asyncio
async def test_one_row_per_contact_however_many_messages(
    client: AsyncClient, two_branches: dict[str, uuid.UUID]
) -> None:
    for n in range(3):
        await post_inbound(
            client, "inst-centro", message_id=f"m{n}", phone="+573001112233"
        )

    candidates = await _candidates_of(two_branches["centro"])
    assert len(candidates) == 1


@pytest.mark.asyncio
async def test_an_opted_out_contact_travels_as_a_fact_not_a_filter(
    client: AsyncClient, two_branches: dict[str, uuid.UUID]
) -> None:
    """La consulta NO filtra el opt-out: lo trae, para que la exclusión se pueda contar.

    Filtrarlo en el SQL haría imposible decir *por qué* la audiencia bajó, y esas cuentas son un
    requisito — sin ellas una lista truncada se presenta como completa.
    """
    await post_inbound(client, "inst-centro", message_id="o1", phone="+573001112233")
    tenant_id = await demo_tenant_id()

    async with SessionFactory() as session:
        repo = SqlAlchemyMessagingRepository(session)
        contact = await repo.find_contact_by_phone(tenant_id, "573001112233")
        assert contact is not None
        assert await repo.set_status_opt_out(tenant_id, contact.id, True)

    candidates = await _candidates_of(two_branches["centro"])
    assert len(candidates) == 1
    assert candidates[0].opted_out is True

    # Y la reducción pura sí lo saca, contándolo.
    audience = _resolve(candidates)
    assert audience.is_empty
    assert audience.excluded_opted_out == 1


@pytest.mark.asyncio
async def test_opting_out_an_unknown_contact_reports_it(
    client: AsyncClient, two_branches: dict[str, uuid.UUID]
) -> None:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        repo = SqlAlchemyMessagingRepository(session)
        assert not await repo.set_status_opt_out(tenant_id, uuid.uuid4(), True)


# --- El número propio en la lista enviada ----------------------------------
AUDIENCE_JIDS = ["573001112233@s.whatsapp.net", "573002223344@s.whatsapp.net"]


def test_the_own_number_goes_first_as_a_full_jid() -> None:
    assert with_own_jid(AUDIENCE_JIDS, "+573000000000") == [
        "573000000000@s.whatsapp.net",
        *AUDIENCE_JIDS,
    ]


def test_the_own_number_is_never_duplicated() -> None:
    jids = ["573001112233@s.whatsapp.net", "573000000000@s.whatsapp.net"]

    assert with_own_jid(jids, "573000000000") == [
        "573000000000@s.whatsapp.net",
        "573001112233@s.whatsapp.net",
    ]


def test_an_own_number_already_given_as_a_jid_is_kept() -> None:
    assert with_own_jid(AUDIENCE_JIDS, "573000000000@s.whatsapp.net")[0] == (
        "573000000000@s.whatsapp.net"
    )


@pytest.mark.parametrize("own", [None, "", "12345@lid"])
def test_without_a_usable_own_number_the_audience_goes_as_is(own: str | None) -> None:
    result = with_own_jid(AUDIENCE_JIDS, own)

    assert result == AUDIENCE_JIDS
    assert result is not AUDIENCE_JIDS  # copia: no muta la audiencia auditada
