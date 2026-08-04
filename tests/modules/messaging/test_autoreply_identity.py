"""Los mensajes automáticos hablan con los datos del Perfil del negocio.

Existe por un fallo concreto: el saludo salía como "Bienvenido a Main Branch" —el nombre que
la semilla le pone a la sucursal— mientras el dueño ya había rellenado el perfil con el
nombre de su restaurante. El dato estaba y el mensaje no lo miraba.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from restaurante.modules.business.infrastructure.models import OperatingHoursModel
from restaurante.modules.messaging.infrastructure.models import (
    WhatsAppAutoreplySettingsModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.modules.messaging.conftest import (
    create_branch,
    create_session_row,
    demo_tenant_id,
    grant_only,
    login,
    post_inbound,
)

pytestmark = pytest.mark.asyncio


async def _name_the_business(
    name: str, *, branch_id: uuid.UUID, branch_name: str, address: str, phone: str
) -> None:
    """Lo que dejaría el Perfil del negocio tras rellenarlo."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        await s.execute(
            update(TenantModel).where(TenantModel.id == tenant_id).values(name=name)
        )
        await s.execute(
            update(BranchModel)
            .where(BranchModel.id == branch_id)
            .values(name=branch_name, address=address, phone=phone)
        )
        await s.commit()


async def _enable_greeting(**over: object) -> None:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        row = (
            await s.execute(
                select(WhatsAppAutoreplySettingsModel).where(
                    WhatsAppAutoreplySettingsModel.tenant_id == tenant_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = WhatsAppAutoreplySettingsModel(tenant_id=tenant_id)
            s.add(row)
        row.greeting_enabled = True
        for key, value in over.items():
            setattr(row, key, value)
        await s.commit()


async def _open_all_week(branch_id: uuid.UUID) -> None:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        for weekday in range(7):
            s.add(
                OperatingHoursModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    weekday=weekday,
                    open_minute=0,
                    close_minute=1439,
                )
            )
        await s.commit()


async def _greeted_branch() -> uuid.UUID:
    branch = await create_branch("centro", primary=True)
    await create_session_row(branch, "inst-centro")
    await _open_all_week(branch)
    return branch


# --- El saludo de fábrica ----------------------------------------------------
async def test_the_default_greeting_uses_the_business_name(
    client: AsyncClient, fake_bridge
) -> None:
    """Sin escribir un texto, el saludo dice cómo se llama el restaurante."""
    branch = await _greeted_branch()
    await _name_the_business(
        "Sabor Costeño",
        branch_id=branch,
        branch_name="Main Branch",
        address="Cra 5 #12-30",
        phone="3001112233",
    )
    await _enable_greeting()

    await post_inbound(client, "inst-centro", message_id="id-1")

    _, text = fake_bridge.sent[0]
    assert "Sabor Costeño" in text
    # Y NO el nombre que la semilla le puso a la sucursal, que es el fallo original.
    assert "Main Branch" not in text


async def test_the_business_name_is_read_at_send_time_not_frozen(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await _greeted_branch()
    await _name_the_business(
        "Nombre Viejo",
        branch_id=branch,
        branch_name="Sede Centro",
        address="Cra 5",
        phone="300",
    )
    await _enable_greeting()
    # El dueño corrige el perfil DESPUÉS de encender el saludo.
    await _name_the_business(
        "Nombre Nuevo",
        branch_id=branch,
        branch_name="Sede Centro",
        address="Cra 5",
        phone="300",
    )

    await post_inbound(client, "inst-centro", message_id="id-1")

    _, text = fake_bridge.sent[0]
    assert "Nombre Nuevo" in text


# --- Los marcadores nuevos ---------------------------------------------------
async def test_the_greeting_can_say_the_address_and_the_phone(
    client: AsyncClient, fake_bridge
) -> None:
    branch = await _greeted_branch()
    await _name_the_business(
        "Sabor Costeño",
        branch_id=branch,
        branch_name="Sede Centro",
        address="Cra 5 #12-30",
        phone="3001112233",
    )
    await _enable_greeting(
        greeting_open_text=(
            "{business_name} — {branch_name}\n{branch_address}\nTel: {branch_phone}"
        )
    )

    await post_inbound(client, "inst-centro", message_id="id-1")

    _, text = fake_bridge.sent[0]
    assert "Sabor Costeño" in text
    assert "Sede Centro" in text
    assert "Cra 5 #12-30" in text
    assert "3001112233" in text


async def test_a_missing_address_leaves_the_placeholder_visible(
    client: AsyncClient, fake_bridge
) -> None:
    """Un hueco a la vista es feo pero depurable; "Estamos en " no lo es."""
    branch = await _greeted_branch()
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as s:
        await s.execute(
            update(TenantModel).where(TenantModel.id == tenant_id).values(name="Sabor")
        )
        await s.execute(
            update(BranchModel).where(BranchModel.id == branch).values(address=None)
        )
        await s.commit()
    await _enable_greeting(greeting_open_text="Estamos en {branch_address}")

    await post_inbound(client, "inst-centro", message_id="id-1")

    _, text = fake_bridge.sent[0]
    assert text == "Estamos en {branch_address}"


# --- La pantalla de ajustes los ofrece ---------------------------------------
async def test_the_settings_api_offers_the_identity_placeholders(
    client: AsyncClient,
) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    body = (await client.get("/messaging/autoreply", headers=headers)).json()

    # Están en los dos sitios: un aviso de "pedido listo" que dice dónde recogerlo es un
    # aviso mejor, así que la identidad vale también en los mensajes de pedido.
    for name in ("business_name", "branch_name", "branch_address", "branch_phone"):
        assert name in body["greeting_placeholders"], name
        assert name in body["order_placeholders"], name


async def test_saving_a_greeting_with_the_identity_placeholders_is_accepted(
    client: AsyncClient,
) -> None:
    await grant_only(["messaging.manage"])
    headers = await login(client)

    resp = await client.put(
        "/messaging/autoreply",
        headers=headers,
        json={
            "greeting_enabled": True,
            "greeting_open_text": "Hola desde {business_name} ({branch_phone})",
            "greeting_closed_text": "Abrimos {next_opening}",
            "assistant_offer_enabled": False,
            "idle_hours": 24,
            "token_lifetime_hours": 24,
            "status_mapping": {
                "ready": {
                    "enabled": True,
                    "text": "Recoge *{order_number}* en {branch_address}",
                }
            },
        },
    )

    assert resp.status_code == 200, resp.text
