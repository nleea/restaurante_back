"""Fixtures de las pruebas de alertas.

El repositorio se prueba contra la base de datos real de la suite (SQLite con el mismo
índice único parcial que Postgres), no contra un doble: lo que se está probando ES la
constraint. Un fake de repositorio validaría el fake.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest_asyncio
from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.alerts.domain.ports import Alert, Subject
from restaurante.modules.identity.infrastructure.models import PersonModel, UserModel
from restaurante.modules.messaging.infrastructure.models import WhatsAppContactModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel

# El escalado se prueba contra el puente FALSO pero el guardián REAL, igual que en messaging:
# lo que se está probando es justamente que el guardián no se salta ni desde dentro del
# sistema. Se reexporta el fixture en vez de duplicarlo para que los dos módulos prueben
# contra el mismo doble.
from tests.modules.messaging.conftest import fake_bridge  # noqa: F401


async def demo_tenant_id() -> uuid.UUID:
    async with SessionFactory() as session:
        stmt = select(TenantModel.id).where(TenantModel.slug == "demo")
        return (await session.execute(stmt)).scalar_one()


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


async def create_employee(branch_id: uuid.UUID, name: str) -> uuid.UUID:
    """Una persona de verdad a la que atribuir la toma de una alerta.

    Con un uuid inventado la FK falla, y esa FK es deliberada: "la tomó Ana" sólo sirve si
    Ana existe. El test pasa por el mismo camino que producción.
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        person = PersonModel(first_name=name, last_name="Pruebas")
        session.add(person)
        await session.flush()
        user = UserModel(
            tenant_id=tenant_id,
            email=f"{name.lower()}-{uuid.uuid4().hex[:6]}@demo.com",
            hashed_password="x",
            name=name,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user.id,
            role_id=roles["admin"].id,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def create_demo_employee(branch_id: uuid.UUID) -> uuid.UUID:
    """Un empleado ligado al usuario que hace login en los tests.

    Distinto de `create_employee`, que fabrica una persona nueva: tomar una alerta se
    atribuye al EMPLEADO de quien está firmado, así que el API necesita que el usuario de la
    sesión tenga empleado en esa sucursal.
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        roles = await seed_rbac(session)
        await session.commit()
        user_id = (
            await session.execute(
                select(UserModel.id).where(UserModel.email == "admin@demo.com")
            )
        ).scalar_one()
        person = PersonModel(first_name="Ana", last_name="Restrepo")
        session.add(person)
        await session.flush()
        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user_id,
            role_id=roles["admin"].id,
            is_active=True,
        )
        session.add(employee)
        await session.commit()
        await session.refresh(employee)
        return employee.id


async def subscribe_to_alerts(employee_id: uuid.UUID, receives: bool = True) -> None:
    """Señala a esta persona para recibir alertas escaladas.

    Es un paso explícito en los tests porque lo es en el producto: tener el permiso ya NO
    basta, precisamente para que ver el panel y recibir un WhatsApp de noche puedan decidirse
    por separado.
    """
    async with SessionFactory() as session:
        employee = await session.get(EmployeeModel, employee_id)
        assert employee is not None
        employee.receives_alerts = receives
        await session.commit()


async def link_chat(employee_id: uuid.UUID, address: str) -> None:
    """Empareja al empleado con el chat de esa dirección (número o `@lid`).

    Es un paso explícito en los tests porque lo es en el producto: por teléfono no se puede
    deducir —WhatsApp manda un `@lid` en modo privacidad y nunca da el número—, así que el
    dueño elige de entre los chats que ya escribieron.
    """
    async with SessionFactory() as session:
        contact_id = (
            await session.execute(
                select(WhatsAppContactModel.id).where(
                    WhatsAppContactModel.phone == address
                )
            )
        ).scalar_one()
        employee = await session.get(EmployeeModel, employee_id)
        assert employee is not None
        employee.whatsapp_contact_id = contact_id
        await session.commit()


class RecordingChannel:
    """Un canal que sólo anota. Puede fallar, porque un canal caído es un caso de diseño."""

    def __init__(self, *, fail: bool = False) -> None:
        self.sent: list[tuple[str, str, str]] = []
        self.fail = fail

    async def notify(self, alert: Alert, subject: Subject, kind: str) -> None:
        if self.fail:
            raise RuntimeError("canal caído")
        self.sent.append((alert.rule_key, subject.ref, kind))


# Las sesiones que abren los helpers de los tests, cerradas al terminar cada uno. Sin esto el
# recolector de basura las suelta a medias y SQLAlchemy avisa de conexiones no devueltas.
OPEN_SESSIONS: list[AsyncSession] = []


def tracked_session() -> AsyncSession:
    """Una sesión que el test no tiene que acordarse de cerrar."""
    session = SessionFactory()
    OPEN_SESSIONS.append(session)
    return session


@pytest_asyncio.fixture(autouse=True)
async def _close_sessions() -> AsyncIterator[None]:
    yield
    while OPEN_SESSIONS:
        await OPEN_SESSIONS.pop().close()


@pytest_asyncio.fixture
async def branch_id(client: AsyncClient) -> AsyncIterator[uuid.UUID]:
    """Una sucursal limpia. `client` arrastra la creación del esquema y del tenant demo."""
    yield await create_branch(f"b{uuid.uuid4().hex[:6]}", primary=True)
