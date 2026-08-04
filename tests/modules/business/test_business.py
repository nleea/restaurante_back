"""Business module: operating-hours CRUD + validation, profile aggregation, and the
public storefront hours endpoint (open-now / next-opening)."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)
from restaurante.modules.business.domain.entities import OperatingHours
from restaurante.modules.business.infrastructure.repositories import (
    SqlAlchemyBusinessRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import NotFoundError, ValidationError
from tests.modules.storefront._seed import demo_tenant_id, seed_primary_branch


def _svc(session: object) -> BusinessService:
    return BusinessService(repo=SqlAlchemyBusinessRepository(session))  # type: ignore[arg-type]


def _win(tenant, branch, weekday, o, c) -> OperatingHours:
    return OperatingHours(
        tenant_id=tenant, branch_id=branch, weekday=weekday, open_minute=o, close_minute=c
    )


async def test_set_and_get_hours_round_trip(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    async with SessionFactory() as session:
        await _svc(session).set_hours(
            tenant_id,
            branch_id,
            [
                _win(tenant_id, branch_id, 0, 8 * 60, 12 * 60),
                _win(tenant_id, branch_id, 0, 14 * 60, 20 * 60),
            ],
        )
    async with SessionFactory() as session:
        hours = await _svc(session).get_hours(tenant_id, branch_id)
    assert [(h.weekday, h.open_minute, h.close_minute) for h in hours] == [
        (0, 480, 720),
        (0, 840, 1200),
    ]


async def test_set_hours_replaces_previous(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    async with SessionFactory() as session:
        svc = _svc(session)
        await svc.set_hours(tenant_id, branch_id, [_win(tenant_id, branch_id, 0, 0, 60)])
    async with SessionFactory() as session:
        svc = _svc(session)
        await svc.set_hours(tenant_id, branch_id, [_win(tenant_id, branch_id, 1, 60, 120)])
    async with SessionFactory() as session:
        hours = await _svc(session).get_hours(tenant_id, branch_id)
    assert [(h.weekday, h.open_minute) for h in hours] == [(1, 60)]  # replaced, not merged


async def test_invalid_window_is_rejected(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    async with SessionFactory() as session:
        with pytest.raises(ValidationError):
            await _svc(session).set_hours(
                tenant_id, branch_id, [_win(tenant_id, branch_id, 9, 0, 60)]  # weekday 9
            )


async def test_profile_aggregates_identity_and_branch(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    async with SessionFactory() as session:
        await _svc(session).set_hours(
            tenant_id, branch_id, [_win(tenant_id, branch_id, 2, 9 * 60, 17 * 60)]
        )
    async with SessionFactory() as session:
        profile = await _svc(session).get_profile(tenant_id)
    assert profile.name == "Demo"  # tenant name from conftest
    primary = next(b for b in profile.branches if b.is_primary)
    assert primary.id == branch_id
    assert [(h.weekday, h.open_minute) for h in primary.hours] == [(2, 540)]


# --- Profile edit ----------------------------------------------------------
async def test_update_profile_edits_tenant_and_branch(client: AsyncClient) -> None:
    import uuid as _uuid

    from restaurante.modules.business.domain.entities import BranchDetailsUpdate

    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    async with SessionFactory() as session:
        await _svc(session).update_profile(
            tenant_id,
            name="Ceviches del Puerto",
            tax_id="900123",
            email="hola@puerto.co",
            phone="3001112233",
            branches=[
                BranchDetailsUpdate(
                    id=branch_id, address="Calle 1 #4-12", phone="3009998877"
                )
            ],
        )
    async with SessionFactory() as session:
        profile = await _svc(session).get_profile(tenant_id)
    assert profile.name == "Ceviches del Puerto"
    assert profile.email == "hola@puerto.co"
    primary = next(b for b in profile.branches if b.id == branch_id)
    assert primary.address == "Calle 1 #4-12"
    assert primary.phone == "3009998877"

    # Unknown branch is rejected.
    async with SessionFactory() as session:
        with pytest.raises(NotFoundError):
            await _svc(session).update_profile(
                tenant_id,
                name="X",
                tax_id=None,
                email=None,
                phone=None,
                branches=[BranchDetailsUpdate(id=_uuid.uuid4(), address="a", phone="b")],
            )


async def test_update_profile_requires_auth(client: AsyncClient) -> None:
    resp = await client.put("/business/profile", json={"name": "X"})
    assert resp.status_code == 401, resp.text  # menu.manage gate, no token


async def test_update_profile_photo_writes_shared_brand_logo(
    client: AsyncClient,
) -> None:
    from restaurante.modules.menu.application.use_cases.manage_appearance import (
        AppearanceService,
    )
    from restaurante.modules.menu.infrastructure.repositories import (
        SqlAlchemyMenuRepository,
    )

    tenant_id = await demo_tenant_id()
    await seed_primary_branch()
    photo = "https://cdn.example.com/logos/t/x.png"
    async with SessionFactory() as session:
        svc = BusinessService(
            repo=SqlAlchemyBusinessRepository(session),
            appearance=AppearanceService(repo=SqlAlchemyMenuRepository(session)),
        )
        await svc.update_profile(
            tenant_id,
            name="Negocio",
            tax_id=None,
            email=None,
            phone=None,
            branches=[],
            photo_url=photo,
        )
    # The profile read (which sources photo from the appearance brand logo) reflects it.
    async with SessionFactory() as session:
        profile = await _svc(session).get_profile(tenant_id)
    assert profile.photo_url == photo


# --- Public storefront hours -----------------------------------------------
async def test_storefront_hours_closed_when_no_hours(client: AsyncClient) -> None:
    await seed_primary_branch()
    resp = await client.get("/storefront/hours")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["isOpenNow"] is False
    assert body["nextOpening"] is None
    assert body["windows"] == []


async def test_storefront_hours_open_all_week(client: AsyncClient) -> None:
    tenant_id = await demo_tenant_id()
    branch_id = await seed_primary_branch()
    # A full 24h window every day → open regardless of the server clock.
    async with SessionFactory() as session:
        await _svc(session).set_hours(
            tenant_id,
            branch_id,
            [_win(tenant_id, branch_id, d, 0, 1440) for d in range(7)],
        )
    resp = await client.get("/storefront/hours")
    assert resp.status_code == 200, resp.text
    assert resp.json()["isOpenNow"] is True
    assert len(resp.json()["windows"]) == 7
