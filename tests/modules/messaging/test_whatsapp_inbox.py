"""Shared inbox: the outbound guard, atomic claiming, reply reconciliation, gating.

The guard tests are the important ones. They assert not only that an unsolicited send
is refused, but that *nothing was transmitted* and that the object the composition root
hands out is the guarded one — a rule that only holds if it cannot be bypassed.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from restaurante.modules.messaging.domain.errors import ContactNotReachableError
from restaurante.modules.messaging.infrastructure.api.deps import (
    build_whatsapp_gateway,
    get_messaging_service,
)
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.modules.messaging.infrastructure.repositories import (
    SqlAlchemyMessagingRepository,
)
from restaurante.modules.messaging.infrastructure.whatsapp.guard import (
    GuardedWhatsAppGateway,
)
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import (
    create_branch,
    create_employee,
    create_other_employee,
    create_session_row,
    grant_only,
    login,
    post_inbound,
)


async def _only_conversation() -> WhatsAppConversationModel:
    async with SessionFactory() as session:
        return (
            await session.execute(select(WhatsAppConversationModel))
        ).scalars().first()


async def _messages() -> list[WhatsAppMessageModel]:
    async with SessionFactory() as session:
        rows = await session.execute(
            select(WhatsAppMessageModel).order_by(WhatsAppMessageModel.sent_at)
        )
        return list(rows.scalars())


# --- 8.6 / 8.7 the outbound invariant ---------------------------------------
async def test_gateway_refuses_a_phone_with_no_contact(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-centro")

    async with SessionFactory() as db:
        repo = SqlAlchemyMessagingRepository(db)
        gateway = build_whatsapp_gateway(repo)
        session = await repo.get_session(
            (await repo.list_sessions((await _tenant_of(session_id))))[0].tenant_id,
            session_id,
        )
        assert session is not None
        with pytest.raises(ContactNotReachableError):
            await gateway.send_text(session, "+573009999999", "hola")

    # Nothing reached the bridge: the refusal happens before any transmission.
    assert fake_bridge.sent == []


async def test_gateway_refuses_a_contact_that_never_wrote(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-centro")

    async with SessionFactory() as db:
        repo = SqlAlchemyMessagingRepository(db)
        tenant_id = await _tenant_of(session_id)
        # A contact row with no inbound message — e.g. imported from somewhere else.
        await repo.find_or_create_contact(tenant_id, "+573008887766", "Importado")
        session = await repo.get_session(tenant_id, session_id)
        assert session is not None
        gateway = build_whatsapp_gateway(repo)
        with pytest.raises(ContactNotReachableError):
            await gateway.send_text(session, "+573008887766", "hola")

    assert fake_bridge.sent == []


async def test_gateway_allows_a_contact_who_wrote_first(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-centro")
    await post_inbound(client, "inst-centro", message_id="g-1", phone="+573001112233")

    async with SessionFactory() as db:
        repo = SqlAlchemyMessagingRepository(db)
        tenant_id = await _tenant_of(session_id)
        session = await repo.get_session(tenant_id, session_id)
        assert session is not None
        gateway = build_whatsapp_gateway(repo)
        provider_id = await gateway.send_text(session, "+573001112233", "claro que sí")

    assert provider_id == "provider-out-1"
    assert fake_bridge.sent == [("+573001112233", "claro que sí")]


# --- Lo último que dijimos ---------------------------------------------------
async def test_last_outbound_content_ignores_what_the_customer_just_wrote(
    client: AsyncClient, fake_bridge
) -> None:
    """La lectura que permite no repetir un aviso automático.

    Lo entrante no cuenta: si contara, el mensaje que acaba de llegar taparía siempre nuestra
    última respuesta y el aviso saldría en cada mensaje — que es justo el bug que esto evita.
    """
    branch = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch, "inst-centro")
    await post_inbound(client, "inst-centro", message_id="m-1", phone="+573001112233")
    tenant_id = await _tenant_of(session_id)
    conversation = await _only_conversation()

    async with SessionFactory() as db:
        repo = SqlAlchemyMessagingRepository(db)
        # Nada ha salido todavía.
        assert await repo.last_outbound_content(tenant_id, conversation.id) is None
        await repo.add_message(
            tenant_id,
            branch,
            conversation.id,
            sender_type="system",
            content="Ahora mismo estamos cerrados. Te respondemos en cuanto abramos.",
        )

    # Otro mensaje del cliente no tapa lo que dijimos.
    await post_inbound(client, "inst-centro", message_id="m-2", phone="+573001112233")
    async with SessionFactory() as db:
        repo = SqlAlchemyMessagingRepository(db)
        last = await repo.last_outbound_content(tenant_id, conversation.id)
        assert last is not None and last.startswith("Ahora mismo estamos cerrados.")

    # Y si contesta una persona, lo último pasa a ser lo suyo. `sent_at` explícito: en SQLite
    # `now()` tiene resolución de segundo y dos inserciones seguidas empatarían.
    async with SessionFactory() as db:
        db.add(
            WhatsAppMessageModel(
                tenant_id=tenant_id,
                branch_id=branch,
                whatsapp_conversation_id=conversation.id,
                sender_type="employee",
                content="Buenas, mañana te ayudo.",
                delivery_state="sent",
                sent_at=datetime.now(UTC) + timedelta(minutes=1),
            )
        )
        await db.commit()

    async with SessionFactory() as db:
        repo = SqlAlchemyMessagingRepository(db)
        assert (
            await repo.last_outbound_content(tenant_id, conversation.id)
            == "Buenas, mañana te ayudo."
        )


async def test_the_composition_root_only_ever_yields_the_guarded_gateway() -> None:
    """The invariant does not depend on callers remembering it."""
    async with SessionFactory() as db:
        repo = SqlAlchemyMessagingRepository(db)
        assert isinstance(build_whatsapp_gateway(repo), GuardedWhatsAppGateway)
        # And the service the API depends on is built from that same factory.
        service = get_messaging_service(db)
        assert isinstance(service._gateway, GuardedWhatsAppGateway)


async def _tenant_of(session_id: uuid.UUID) -> uuid.UUID:
    from restaurante.modules.messaging.infrastructure.models import (
        WhatsAppSessionModel,
    )

    async with SessionFactory() as db:
        row = (
            await db.execute(
                select(WhatsAppSessionModel)
                .where(WhatsAppSessionModel.id == session_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).scalar_one()
        return row.tenant_id


# --- 8.8 atomic claiming -----------------------------------------------------
async def test_two_simultaneous_claims_leave_exactly_one_winner(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    conversation = await _only_conversation()
    branch_id = inbox["branch_id"]
    other = await create_other_employee(branch_id, "bruno@demo.com")

    async def claim_as(employee_id: uuid.UUID) -> bool:
        async with SessionFactory() as db:
            repo = SqlAlchemyMessagingRepository(db)
            tenant_id = conversation.tenant_id
            got = await repo.claim_conversation(tenant_id, conversation.id, employee_id)
            return got is not None

    results = await asyncio.gather(
        claim_as(inbox["employee_id"]), claim_as(other), return_exceptions=True
    )
    wins = [r for r in results if r is True]
    assert len(wins) == 1, f"expected exactly one winner, got {results}"


async def test_losing_a_claim_is_a_409_naming_the_holder(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    conversation = await _only_conversation()
    other = await create_other_employee(inbox["branch_id"], "bruno@demo.com")

    # Somebody else got there first.
    async with SessionFactory() as db:
        await db.execute(
            update(WhatsAppConversationModel)
            .where(WhatsAppConversationModel.id == conversation.id)
            .values(employee_id=other, status="human")
        )
        await db.commit()

    resp = await client.post(
        f"/messaging/conversations/{conversation.id}/claim",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "conversation_already_claimed"
    # Told by whom — otherwise the agent has nothing to act on.
    assert body["holder_employee_id"] == str(other)
    assert body["holder_name"] == "Bruno Díaz"
    assert "Bruno Díaz" in body["detail"]


async def test_claiming_assigns_the_employee_and_marks_it_human(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    conversation = await _only_conversation()
    resp = await client.post(
        f"/messaging/conversations/{conversation.id}/claim",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "human"
    assert body["employee_id"] == str(inbox["employee_id"])
    assert body["holder_name"] == "Ana Restrepo"


# --- 8.9 reply reconciliation ------------------------------------------------
async def test_reply_is_attributed_and_marked_sent(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge
) -> None:
    conversation = await _only_conversation()
    resp = await client.post(
        f"/messaging/conversations/{conversation.id}/messages",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
        json={"body": "Sí, tenemos domicilio."},
    )
    assert resp.status_code == 201, resp.text

    outbound = [m for m in await _messages() if m.sender_type == "employee"]
    assert len(outbound) == 1
    assert outbound[0].employee_id == inbox["employee_id"]
    assert outbound[0].delivery_state == "sent"
    assert outbound[0].provider_message_id == "provider-out-1"
    # Sin el `+`: el teléfono se guarda en forma canónica (sólo dígitos), que es como lo
    # manda WhatsApp en el JID y como hay que devolvérselo. Un `+` en un JID no existe.
    assert fake_bridge.sent == [("573001112233", "Sí, tenemos domicilio.")]


async def test_a_reply_the_bridge_rejects_stays_visible_as_failed(
    client: AsyncClient, inbox: dict[str, Any], fake_bridge
) -> None:
    fake_bridge.fail = True
    conversation = await _only_conversation()

    resp = await client.post(
        f"/messaging/conversations/{conversation.id}/messages",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
        json={"body": "esto no va a salir"},
    )
    assert resp.status_code == 502, resp.text
    assert resp.json()["code"] == "message_delivery_failed"

    # The whole point: the agent must be able to see that it did not land.
    outbound = [m for m in await _messages() if m.sender_type == "employee"]
    assert len(outbound) == 1
    assert outbound[0].delivery_state == "failed"
    assert outbound[0].content == "esto no va a salir"

    thread = await client.get(
        f"/messaging/conversations/{conversation.id}",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
    )
    states = [m["delivery_state"] for m in thread.json()["messages"]]
    assert "failed" in states


# --- 8.10 the doorbell -------------------------------------------------------
async def test_inbound_publishes_the_doorbell_for_its_tenant_and_branch(
    client: AsyncClient, publisher
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    await post_inbound(client, "inst-centro", message_id="d-1")

    assert len(publisher.published) == 1
    topic, _tenant_id, branch_id, payload = publisher.published[0]
    assert topic == "whatsapp_inbox"
    assert branch_id == branch
    assert "conversation_id" in payload


async def test_a_broken_broker_does_not_lose_the_message(
    client: AsyncClient, publisher
) -> None:
    publisher.fail = True
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    resp = await post_inbound(client, "inst-centro", message_id="d-2")

    # The message is committed before the doorbell rings, so a dead broker only costs
    # the live refresh — the inbox still finds it on its polling interval.
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "stored"
    assert len([m for m in await _messages() if m.sender_type == "contact"]) == 1


# --- inbox reads -------------------------------------------------------------
async def test_inbox_lists_only_the_requested_branch(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    norte = await create_branch("norte")
    await create_session_row(norte, "inst-norte")
    await post_inbound(
        client, "inst-norte", message_id="n-1", phone="+573005554433"
    )

    centro_list = await client.get(
        "/messaging/conversations",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
    )
    assert centro_list.status_code == 200, centro_list.text
    rows = centro_list.json()
    assert len(rows) == 1
    assert rows[0]["contact_phone"] == "573001112233"
    assert rows[0]["awaiting_reply"] is True
    assert rows[0]["last_message_preview"] == "Hola, ¿tienen domicilio?"

    norte_list = await client.get(
        "/messaging/conversations",
        headers=inbox["headers"],
        params={"branch_id": str(norte)},
    )
    assert [r["contact_phone"] for r in norte_list.json()] == ["573005554433"]


async def test_a_closed_conversation_leaves_the_open_list(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    conversation = await _only_conversation()
    resp = await client.post(
        f"/messaging/conversations/{conversation.id}/close",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "closed"

    listed = await client.get(
        "/messaging/conversations",
        headers=inbox["headers"],
        params={"branch_id": str(inbox["branch_id"])},
    )
    assert listed.json() == []


async def test_a_conversation_of_another_branch_is_not_readable(
    client: AsyncClient, inbox: dict[str, Any]
) -> None:
    conversation = await _only_conversation()
    other = await create_branch("norte")

    resp = await client.get(
        f"/messaging/conversations/{conversation.id}",
        headers=inbox["headers"],
        params={"branch_id": str(other)},
    )
    # 404 rather than 403: an inbox scoped to one branch should not confirm that a
    # conversation exists on another.
    assert resp.status_code == 404


# --- 8.11 permission gating --------------------------------------------------
async def test_read_permission_alone_cannot_claim_reply_or_close(
    client: AsyncClient,
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await create_employee(branch, "ana@demo.com")
    await post_inbound(client, "inst-centro", message_id="p-1")
    conversation = await _only_conversation()

    await grant_only(["messaging.read"])
    headers = await login(client)
    params = {"branch_id": str(branch)}

    listed = await client.get(
        "/messaging/conversations", headers=headers, params=params
    )
    assert listed.status_code == 200
    thread = await client.get(
        f"/messaging/conversations/{conversation.id}", headers=headers, params=params
    )
    assert thread.status_code == 200

    for path, payload in (
        (f"/messaging/conversations/{conversation.id}/claim", None),
        (f"/messaging/conversations/{conversation.id}/messages", {"body": "hola"}),
        (f"/messaging/conversations/{conversation.id}/close", None),
    ):
        resp = await client.post(
            path, headers=headers, params=params, json=payload
        )
        assert resp.status_code == 403, f"{path} -> {resp.status_code}"


async def test_without_read_the_inbox_is_refused(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    await grant_only(["orders.read"])
    headers = await login(client)

    resp = await client.get(
        "/messaging/conversations",
        headers=headers,
        params={"branch_id": str(branch)},
    )
    assert resp.status_code == 403


async def test_sessions_require_manage(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    await grant_only(["messaging.read", "messaging.attend"])
    headers = await login(client)

    listed = await client.get("/messaging/sessions", headers=headers)
    assert listed.status_code == 403

    created = await client.post(
        "/messaging/sessions",
        headers=headers,
        json={"branch_id": str(branch), "provider_instance_ref": "inst-x"},
    )
    assert created.status_code == 403


async def test_manage_can_pair_a_branch(client: AsyncClient, fake_bridge) -> None:
    branch = await create_branch("centro", primary=True)
    await grant_only(["messaging.manage"])
    headers = await login(client)

    created = await client.post(
        "/messaging/sessions",
        headers=headers,
        json={"branch_id": str(branch), "provider_instance_ref": "inst-centro"},
    )
    assert created.status_code == 201, created.text
    assert created.json()["status"] == "disconnected"
    session_id = created.json()["id"]

    paired = await client.post(
        f"/messaging/sessions/{session_id}/pair", headers=headers
    )
    assert paired.status_code == 200, paired.text
    assert paired.json()["session"]["status"] == "qr_pending"
    # El QR viaja con la respuesta: la pantalla no tiene que pedirlo aparte.
    assert paired.json()["qr"] == "data:image/png;base64,QRFAKE"
    # Y el webhook queda registrado EN EL MISMO PASO: un número emparejado sin webhook
    # recibe mensajes que no llegan a ninguna parte.
    assert len(fake_bridge.paired) == 1
    instance_ref, webhook_url, secret = fake_bridge.paired[0]
    assert instance_ref == "inst-centro"
    assert webhook_url.endswith("/webhooks/whatsapp/inst-centro")
    assert secret == "test-webhook-secret"

    connected = await client.patch(
        f"/messaging/sessions/{session_id}/status",
        headers=headers,
        json={"status": "connected", "phone_number": "+573001234567"},
    )
    assert connected.json()["status"] == "connected"
    assert connected.json()["phone_number"] == "+573001234567"
    # Credentials are never part of the record.
    assert "credentials" not in connected.json()
    assert "token" not in connected.json()


async def test_a_branch_cannot_have_two_sessions(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    await grant_only(["messaging.manage"])
    headers = await login(client)

    first = await client.post(
        "/messaging/sessions",
        headers=headers,
        json={"branch_id": str(branch), "provider_instance_ref": "inst-a"},
    )
    assert first.status_code == 201
    second = await client.post(
        "/messaging/sessions",
        headers=headers,
        json={"branch_id": str(branch), "provider_instance_ref": "inst-b"},
    )
    assert second.status_code == 409
