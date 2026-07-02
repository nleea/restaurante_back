"""Integration tests for the authentication endpoints (app + sqlite DB)."""

from __future__ import annotations

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from restaurante.main import app
from restaurante.shared.audit.models import AuditLogModel
from restaurante.shared.database import SessionFactory
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def test_login_ok(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"


async def test_login_invalid_password(client: AsyncClient) -> None:
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": "wrong"}
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_error"


async def test_login_unknown_tenant(setup_db: None) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://unknown.api.local"
    ) as c:
        resp = await c.post(
            "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
    assert resp.status_code == 404
    assert resp.json()["code"] == "tenant_not_resolved"


async def test_me_with_token(client: AsyncClient) -> None:
    login = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    access = login.json()["access_token"]

    resp = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert resp.status_code == 200
    assert resp.json()["email"] == TEST_EMAIL


async def test_me_without_token(client: AsyncClient) -> None:
    resp = await client.get("/auth/me")
    assert resp.status_code == 401


async def test_refresh_rotates_tokens(client: AsyncClient) -> None:
    login = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    refresh_token = login.json()["refresh_token"]

    resp = await client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]


async def test_refresh_rejects_access_token(client: AsyncClient) -> None:
    login = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    access = login.json()["access_token"]

    resp = await client.post("/auth/refresh", json={"refresh_token": access})
    assert resp.status_code == 401
    assert resp.json()["code"] == "invalid_token"


async def _audit_actions() -> list[str]:
    # Outside a request there is no tenant in context, so the filter is a no-op
    # and returns all recorded rows.
    async with SessionFactory() as session:
        rows = (
            await session.execute(select(AuditLogModel.action))
        ).scalars().all()
    return list(rows)


async def test_login_ok_records_audit(client: AsyncClient) -> None:
    await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert "login.success" in await _audit_actions()


async def test_login_failure_records_audit(client: AsyncClient) -> None:
    await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": "wrong"}
    )
    assert "login.failure" in await _audit_actions()
