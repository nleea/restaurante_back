"""Tests unitarios del LoginUseCase con dobles de prueba (sin DB ni JWT real)."""

from __future__ import annotations

import uuid

import pytest

from restaurante.modules.identity.application.use_cases.login import (
    LOGIN_FAILURE,
    LOGIN_SUCCESS,
    LoginUseCase,
)
from restaurante.modules.identity.domain.entities import User
from restaurante.shared.domain.audit import AuditEvent
from restaurante.shared.domain.errors import AuthenticationError

TENANT_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


class FakeUserRepository:
    def __init__(self, user: User | None) -> None:
        self._user = user

    async def get_by_email(self, tenant_id: uuid.UUID, email: str) -> User | None:
        if self._user and self._user.tenant_id == tenant_id and self._user.email == email:
            return self._user
        return None

    async def get_by_id(self, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User | None:
        return self._user


class FakeHasher:
    def hash(self, plain: str) -> str:
        return f"hashed:{plain}"

    def verify(self, plain: str, hashed: str) -> bool:
        return hashed == f"hashed:{plain}"


class FakeTokens:
    def create_access_token(self, subject: uuid.UUID, tenant_id: uuid.UUID) -> str:
        return f"access:{subject}:{tenant_id}"

    def create_refresh_token(self, subject: uuid.UUID, tenant_id: uuid.UUID) -> str:
        return f"refresh:{subject}:{tenant_id}"

    def decode(self, token: str) -> dict:
        return {}


class FakeAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    async def record(self, event: AuditEvent) -> None:
        self.events.append(event)


def _user(active: bool = True) -> User:
    return User(
        id=USER_ID,
        tenant_id=TENANT_ID,
        email="admin@demo.com",
        hashed_password="hashed:secret123",
        name="Admin",
        is_active=active,
    )


async def test_login_ok_emite_par_de_tokens() -> None:
    use_case = LoginUseCase(FakeUserRepository(_user()), FakeHasher(), FakeTokens())

    tokens = await use_case.execute(TENANT_ID, "admin@demo.com", "secret123")

    assert tokens.access_token == f"access:{USER_ID}:{TENANT_ID}"
    assert tokens.refresh_token == f"refresh:{USER_ID}:{TENANT_ID}"
    assert tokens.token_type == "bearer"


async def test_login_password_incorrecto() -> None:
    use_case = LoginUseCase(FakeUserRepository(_user()), FakeHasher(), FakeTokens())

    with pytest.raises(AuthenticationError):
        await use_case.execute(TENANT_ID, "admin@demo.com", "wrong")


async def test_login_user_not_found() -> None:
    use_case = LoginUseCase(FakeUserRepository(None), FakeHasher(), FakeTokens())

    with pytest.raises(AuthenticationError):
        await use_case.execute(TENANT_ID, "nadie@demo.com", "secret123")


async def test_login_user_inactive() -> None:
    use_case = LoginUseCase(
        FakeUserRepository(_user(active=False)), FakeHasher(), FakeTokens()
    )

    with pytest.raises(AuthenticationError):
        await use_case.execute(TENANT_ID, "admin@demo.com", "secret123")


async def test_login_normaliza_email() -> None:
    use_case = LoginUseCase(FakeUserRepository(_user()), FakeHasher(), FakeTokens())

    tokens = await use_case.execute(TENANT_ID, "  ADMIN@Demo.com ", "secret123")

    assert tokens.access_token.startswith("access:")


async def test_login_ok_audita_exito() -> None:
    audit = FakeAudit()
    use_case = LoginUseCase(
        FakeUserRepository(_user()), FakeHasher(), FakeTokens(), audit=audit
    )

    await use_case.execute(TENANT_ID, "admin@demo.com", "secret123", ip="10.0.0.1")

    assert len(audit.events) == 1
    event = audit.events[0]
    assert event.action == LOGIN_SUCCESS
    assert event.tenant_id == TENANT_ID
    assert event.actor_id == USER_ID
    assert event.ip == "10.0.0.1"


async def test_login_fallido_audita_fracaso() -> None:
    audit = FakeAudit()
    use_case = LoginUseCase(
        FakeUserRepository(_user()), FakeHasher(), FakeTokens(), audit=audit
    )

    with pytest.raises(AuthenticationError):
        await use_case.execute(TENANT_ID, "admin@demo.com", "wrong")

    assert len(audit.events) == 1
    assert audit.events[0].action == LOGIN_FAILURE
    # En fallo por password sí conocemos al actor.
    assert audit.events[0].actor_id == USER_ID


async def test_login_user_not_found_audits_without_actor() -> None:
    audit = FakeAudit()
    use_case = LoginUseCase(
        FakeUserRepository(None), FakeHasher(), FakeTokens(), audit=audit
    )

    with pytest.raises(AuthenticationError):
        await use_case.execute(TENANT_ID, "nadie@demo.com", "secret123")

    assert len(audit.events) == 1
    assert audit.events[0].action == LOGIN_FAILURE
    assert audit.events[0].actor_id is None
