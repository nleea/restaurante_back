"""Shared fixtures for the messaging tests.

The bridge is never contacted: `fake_bridge` patches `BridgeWhatsAppGateway.send_text`
only. The guard around it stays real, so every outbound test exercises the actual
wiring rather than a stand-in for it.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.messaging.application.use_cases import manage_messaging
from restaurante.modules.messaging.domain.errors import (
    MediaUnavailableError,
    MessageDeliveryError,
)
from restaurante.modules.messaging.infrastructure.models import WhatsAppSessionModel
from restaurante.modules.messaging.infrastructure.whatsapp import bridge as bridge_mod
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.realtime import deps as realtime_deps
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD

WEBHOOK_SECRET = "test-webhook-secret"
SECRET_HEADER = {"X-Webhook-Secret": WEBHOOK_SECRET}


@dataclass
class FakeBridge:
    """Records what would have been transmitted, and can be told to fail."""

    sent: list[tuple[str, str]] = field(default_factory=list)
    fail: bool = False
    next_message_id: str = "provider-out-1"
    # Lo que Evolution devolvería al conectar: un PNG en data-URI, o None si ya conectada.
    next_qr: str | None = "data:image/png;base64,QRFAKE"
    paired: list[tuple[str, str, str]] = field(default_factory=list)
    # Multimedia entrante: los bytes que devolvería, y cada clave que se le pidió. La LISTA es la
    # aserción de varias pruebas — "no se pidió nada" es lo que demuestra que se decidió con el
    # sobre y sin descargar.
    next_media: bytes | None = b"\xff\xd8\xff bytes de una foto"
    #: Lo que SALIÓ con archivo: `(teléfono, mimetype, nombre, pie)`. Que esté vacío es la
    #: aserción de varias pruebas — "no se mandó nada" es lo que demuestra que se rechazó antes.
    media_sent: list[tuple[str, str, str, str]] = field(default_factory=list)
    media_requests: list[tuple[str, str]] = field(default_factory=list)
    media_fails: bool = False

    async def record(self, to_phone: str, body: str) -> str:
        if self.fail:
            raise MessageDeliveryError("El puente rechazó el envío.")
        self.sent.append((to_phone, body))
        return self.next_message_id

    async def record_media(
        self, to_phone: str, mimetype: str, filename: str, caption: str
    ) -> str:
        if self.fail:
            raise MessageDeliveryError("El puente rechazó el envío.")
        self.media_sent.append((to_phone, mimetype, filename, caption))
        return self.next_message_id

    async def give_media(self, provider_message_id: str, remote_jid: str) -> bytes:
        self.media_requests.append((provider_message_id, remote_jid))
        if self.media_fails or self.next_media is None:
            raise MediaUnavailableError("El puente no devolvió el archivo del mensaje.")
        return self.next_media


@dataclass
class RecordingPublisher:
    """Stands in for the realtime doorbell; `fail` makes every publish raise."""

    published: list[tuple[str, uuid.UUID, uuid.UUID, dict[str, Any]]] = field(
        default_factory=list
    )
    fail: bool = False

    async def publish(
        self,
        topic: str,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        payload: dict[str, Any],
    ) -> None:
        if self.fail:
            raise RuntimeError("broker caído")
        self.published.append((topic, tenant_id, branch_id, payload))


@pytest.fixture
def fake_bridge(monkeypatch: pytest.MonkeyPatch) -> FakeBridge:
    """Replace ONLY the bridge's transmission. The guard around it stays real.

    Patched with a plain function so Python's descriptor protocol binds the gateway
    instance to `_bridge_self`; assigning a bound method here silently shifts every
    argument by one.
    """
    fake = FakeBridge()

    async def _send_text(
        _bridge_self: Any, _session: Any, to_phone: str, body: str
    ) -> str:
        return await fake.record(to_phone, body)

    async def _start_pairing(
        _bridge_self: Any, session: Any, webhook_url: str, webhook_secret: str
    ) -> str | None:
        fake.paired.append(
            (session.provider_instance_ref, webhook_url, webhook_secret)
        )
        return fake.next_qr

    monkeypatch.setattr(
        bridge_mod.BridgeWhatsAppGateway, "send_text", _send_text, raising=True
    )
    async def _fetch_media(
        _bridge_self: Any,
        _session: Any,
        provider_message_id: str,
        remote_jid: str,
        *,
        from_me: bool = False,
    ) -> bytes:
        return await fake.give_media(provider_message_id, remote_jid)

    monkeypatch.setattr(
        bridge_mod.BridgeWhatsAppGateway, "start_pairing", _start_pairing, raising=True
    )
    async def _send_media(
        _bridge_self: Any,
        _session: Any,
        to_phone: str,
        _data: bytes,
        *,
        mimetype: str,
        filename: str,
        caption: str = "",
    ) -> str:
        return await fake.record_media(to_phone, mimetype, filename, caption)

    monkeypatch.setattr(
        bridge_mod.BridgeWhatsAppGateway, "fetch_media", _fetch_media, raising=True
    )
    monkeypatch.setattr(
        bridge_mod.BridgeWhatsAppGateway, "send_media", _send_media, raising=True
    )
    return fake


@dataclass
class MediaSink:
    """Sustituye la subida a R2 y registra lo que le llegó.

    Se finge la SUBIDA y no el almacenamiento entero a propósito: lo que estas pruebas miran es el
    engarce —el orden, los gates, la redistribución, el fallo— y no R2. La función de guardado
    tiene sus propias pruebas con dobles en `test_media_store.py`.
    """

    stored: list[tuple[str, int]] = field(default_factory=list)
    url: str | None = "https://cdn.test/whatsapp-media/foto.jpg"

    async def store(
        self,
        tenant_id: Any,
        conversation_id: Any,
        mimetype: str,
        data: bytes,
        *,
        storage: Any,
        now: Any = None,
        client: Any = None,
    ) -> str | None:
        self.stored.append((mimetype, len(data)))
        return self.url


@pytest.fixture
def media_sink(monkeypatch: pytest.MonkeyPatch) -> MediaSink:
    """Intercepta la subida del archivo entrante en el punto donde el servicio la llama."""
    sink = MediaSink()
    monkeypatch.setattr(
        manage_messaging, "store_conversation_media", sink.store, raising=True
    )
    return sink


@pytest.fixture
def publisher(monkeypatch: pytest.MonkeyPatch) -> Iterator[RecordingPublisher]:
    recorder = RecordingPublisher()
    monkeypatch.setattr(realtime_deps, "_event_publisher", recorder, raising=False)
    yield recorder
    monkeypatch.setattr(realtime_deps, "_event_publisher", None, raising=False)


async def demo_tenant_id() -> uuid.UUID:
    async with SessionFactory() as session:
        tenant = (
            await session.execute(select(TenantModel).where(TenantModel.slug == "demo"))
        ).scalar_one()
        return tenant.id


async def demo_user_id() -> uuid.UUID:
    async with SessionFactory() as session:
        user = (
            await session.execute(
                select(UserModel).where(UserModel.email == TEST_EMAIL)
            )
        ).scalar_one()
        return user.id


async def assign_role(role_name: str) -> uuid.UUID:
    tenant_id = await demo_tenant_id()
    user_id = await demo_user_id()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        await SqlAlchemyRbacRepository(session).assign_user_role(
            tenant_id, user_id, roles[role_name].id
        )
        return roles[role_name].id


async def grant_only(codes: list[str]) -> None:
    """Leave the demo user holding exactly `codes` and nothing else.

    Revoking first is essential: effective permissions are the UNION of a user's roles,
    so a lingering `admin` from fixture setup would make every gating assertion pass
    for the wrong reason.
    """
    tenant_id = await demo_tenant_id()
    user_id = await demo_user_id()
    async with SessionFactory() as session:
        await seed_rbac(session)
        await session.commit()
        repo = SqlAlchemyRbacRepository(session)
        for existing in await repo.get_user_roles(tenant_id, user_id):
            await repo.revoke_user_role(tenant_id, user_id, existing.id)
        await session.commit()
        role = await repo.create_role(tenant_id, f"custom-{uuid.uuid4().hex[:8]}", None)
        wanted = {c for c in codes}
        permission_ids = [
            p.id for p in await repo.list_permissions() if p.code in wanted
        ]
        await repo.set_role_permissions(role.id, permission_ids)
        await repo.assign_user_role(tenant_id, user_id, role.id)
        await session.commit()


async def login(client: AsyncClient) -> dict[str, str]:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def create_branch(code: str, *, primary: bool = False) -> uuid.UUID:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id,
            code=code,
            name=f"Sede {code}",
            is_active=True,
            is_primary=primary,
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return branch.id


async def create_session_row(
    branch_id: uuid.UUID, instance_ref: str, status: str = "connected"
) -> uuid.UUID:
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        row = WhatsAppSessionModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            provider_instance_ref=instance_ref,
            status=status,
            phone_number="+573000000000",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def create_employee(branch_id: uuid.UUID, email: str) -> uuid.UUID:
    """An employee for the signed-in demo user, so claiming/replying can attribute."""
    tenant_id = await demo_tenant_id()
    user_id = await demo_user_id()
    role_id = await assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Ana", last_name="Restrepo")
        session.add(person)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user_id,
            role_id=role_id,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def create_other_employee(branch_id: uuid.UUID, email: str) -> uuid.UUID:
    """A second employee, used to simulate somebody else winning a claim."""
    tenant_id = await demo_tenant_id()
    role_id = await assign_role("admin")
    async with SessionFactory() as session:
        person = PersonModel(first_name="Bruno", last_name="Díaz")
        session.add(person)
        await session.flush()
        user = UserModel(
            tenant_id=tenant_id,
            email=email,
            hashed_password="x",
            name="Bruno Díaz",
            is_active=True,
        )
        session.add(user)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user.id,
            role_id=role_id,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def post_inbound(
    client: AsyncClient,
    instance_ref: str,
    *,
    message_id: str,
    phone: str = "+573001112233",
    text: str = "Hola, ¿tienen domicilio?",
    message_type: str = "text",
    secret: str | None = WEBHOOK_SECRET,
) -> Any:
    headers = {"X-Webhook-Secret": secret} if secret is not None else {}
    return await client.post(
        f"/webhooks/whatsapp/{instance_ref}",
        headers=headers,
        json={
            "id": message_id,
            "from": phone,
            "text": text,
            "type": message_type,
        },
    )


@pytest_asyncio.fixture
async def inbox(client: AsyncClient) -> AsyncIterator[dict[str, Any]]:
    """A branch with a paired session, an employee, and one inbound message."""
    branch_id = await create_branch("centro", primary=True)
    session_id = await create_session_row(branch_id, "inst-centro")
    employee_id = await create_employee(branch_id, TEST_EMAIL)
    headers = await login(client)
    await post_inbound(client, "inst-centro", message_id="in-1")
    yield {
        "branch_id": branch_id,
        "session_id": session_id,
        "employee_id": employee_id,
        "headers": headers,
    }
