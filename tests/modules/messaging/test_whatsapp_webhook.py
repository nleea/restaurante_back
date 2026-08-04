"""Inbound webhook: branch scoping, idempotency, contact reuse, the idle window.

These cover the properties that make an unofficial bridge survivable — it redelivers,
it knows nothing about our branches, and it is the only thing that decides when a
message arrives.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import func, select, update

from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppContactModel,
    WhatsAppConversationModel,
    WhatsAppMessageModel,
)
from restaurante.shared.database import SessionFactory
from tests.modules.messaging.conftest import (
    create_branch,
    create_session_row,
    post_inbound,
)


async def _count(model: type) -> int:
    async with SessionFactory() as session:
        return (
            await session.execute(select(func.count()).select_from(model))
        ).scalar_one()


async def _messages_of(conversation_id: uuid.UUID) -> list[WhatsAppMessageModel]:
    async with SessionFactory() as session:
        rows = await session.execute(
            select(WhatsAppMessageModel)
            .where(WhatsAppMessageModel.whatsapp_conversation_id == conversation_id)
            .order_by(WhatsAppMessageModel.sent_at)
        )
        return list(rows.scalars())


async def _conversations() -> list[WhatsAppConversationModel]:
    async with SessionFactory() as session:
        rows = await session.execute(
            select(WhatsAppConversationModel).order_by(
                WhatsAppConversationModel.started_at
            )
        )
        return list(rows.scalars())


# --- 8.1 branch scoping ------------------------------------------------------
async def test_message_lands_on_the_sessions_branch_not_the_primary(
    client: AsyncClient,
) -> None:
    primary = await create_branch("principal", primary=True)
    norte = await create_branch("norte")
    await create_session_row(norte, "inst-norte")

    resp = await post_inbound(client, "inst-norte", message_id="m-1")
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "stored"

    conversations = await _conversations()
    assert len(conversations) == 1
    # The customer picked the branch by picking the number.
    assert conversations[0].branch_id == norte
    assert conversations[0].branch_id != primary

    messages = await _messages_of(conversations[0].id)
    assert [m.branch_id for m in messages] == [norte]
    assert messages[0].sender_type == "contact"
    assert messages[0].delivery_state == "sent"


# --- 8.2 idempotency ---------------------------------------------------------
async def test_same_provider_message_id_three_times_stores_one_message(
    client: AsyncClient,
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    statuses = []
    for _ in range(3):
        resp = await post_inbound(client, "inst-centro", message_id="dup-1")
        assert resp.status_code == 200, resp.text
        statuses.append(resp.json()["status"])

    # Every attempt answers 200 — a 4xx would make the bridge retry forever.
    assert statuses == ["stored", "duplicate", "duplicate"]
    assert await _count(WhatsAppMessageModel) == 1
    assert await _count(WhatsAppConversationModel) == 1


async def test_redelivery_does_not_ring_the_doorbell_twice(
    client: AsyncClient, publisher
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    await post_inbound(client, "inst-centro", message_id="dup-2")
    await post_inbound(client, "inst-centro", message_id="dup-2")

    assert len(publisher.published) == 1


# --- 8.3 rejection paths -----------------------------------------------------
async def test_unknown_instance_ref_persists_nothing(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    resp = await post_inbound(client, "inst-desconocida", message_id="x-1")

    # 200 so the bridge stops retrying a message we will never accept.
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert await _count(WhatsAppMessageModel) == 0
    assert await _count(WhatsAppContactModel) == 0


async def test_wrong_or_missing_secret_persists_nothing(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    wrong = await post_inbound(
        client, "inst-centro", message_id="x-2", secret="no-es-el-secreto"
    )
    assert wrong.status_code == 401

    missing = await post_inbound(
        client, "inst-centro", message_id="x-3", secret=None
    )
    assert missing.status_code == 401

    assert await _count(WhatsAppMessageModel) == 0
    assert await _count(WhatsAppConversationModel) == 0
    assert await _count(WhatsAppContactModel) == 0


async def test_unparseable_payload_is_acknowledged_without_persisting(
    client: AsyncClient,
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    resp = await client.post(
        "/webhooks/whatsapp/inst-centro",
        headers={"X-Webhook-Secret": "test-webhook-secret"},
        json={"text": "sin id ni remitente"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    assert await _count(WhatsAppMessageModel) == 0


# --- 8.4 contacts ------------------------------------------------------------
async def test_contact_is_created_once_and_reused(client: AsyncClient) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    await post_inbound(client, "inst-centro", message_id="c-1", phone="+573001112233")
    await post_inbound(client, "inst-centro", message_id="c-2", phone="+573001112233")

    assert await _count(WhatsAppContactModel) == 1
    assert await _count(WhatsAppConversationModel) == 1
    assert await _count(WhatsAppMessageModel) == 2


async def test_same_phone_on_two_branches_is_one_contact_two_conversations(
    client: AsyncClient,
) -> None:
    centro = await create_branch("centro", primary=True)
    norte = await create_branch("norte")
    await create_session_row(centro, "inst-centro")
    await create_session_row(norte, "inst-norte")

    await post_inbound(client, "inst-centro", message_id="b-1", phone="+573009998877")
    await post_inbound(client, "inst-norte", message_id="b-2", phone="+573009998877")

    # One person for the business, one thread per branch they wrote to.
    assert await _count(WhatsAppContactModel) == 1
    conversations = await _conversations()
    assert {c.branch_id for c in conversations} == {centro, norte}
    assert len(conversations) == 2


# --- 8.5 idle window ---------------------------------------------------------
async def test_message_within_the_idle_window_joins_the_conversation(
    client: AsyncClient,
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    await post_inbound(client, "inst-centro", message_id="i-1")
    await post_inbound(client, "inst-centro", message_id="i-2")

    conversations = await _conversations()
    assert len(conversations) == 1
    assert len(await _messages_of(conversations[0].id)) == 2


async def test_message_past_the_idle_window_opens_a_new_conversation(
    client: AsyncClient,
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await post_inbound(client, "inst-centro", message_id="i-3")

    first = (await _conversations())[0]
    # Age the thread past the 24h default rather than waiting for it.
    stale = datetime.now(UTC) - timedelta(hours=30)
    async with SessionFactory() as session:
        await session.execute(
            update(WhatsAppMessageModel)
            .where(WhatsAppMessageModel.whatsapp_conversation_id == first.id)
            .values(sent_at=stale)
        )
        await session.execute(
            update(WhatsAppConversationModel)
            .where(WhatsAppConversationModel.id == first.id)
            .values(started_at=stale)
        )
        await session.commit()

    await post_inbound(client, "inst-centro", message_id="i-4")

    conversations = await _conversations()
    assert len(conversations) == 2
    previous = next(c for c in conversations if c.id == first.id)
    fresh = next(c for c in conversations if c.id != first.id)
    # The old thread is closed, not left dangling open alongside the new one.
    assert previous.status == "closed"
    assert previous.closed_at is not None
    assert fresh.status == "new"


# --- unsupported media -------------------------------------------------------
async def test_unsupported_media_is_stored_as_a_placeholder(
    client: AsyncClient,
) -> None:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")

    resp = await post_inbound(
        client, "inst-centro", message_id="img-1", text=None, message_type="image"
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "stored"

    conversation = (await _conversations())[0]
    messages = await _messages_of(conversation.id)
    # The thread stays coherent: the agent sees that something arrived.
    assert "imagen" in messages[0].content
    assert messages[0].sender_type == "contact"
