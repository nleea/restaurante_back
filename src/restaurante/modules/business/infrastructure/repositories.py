"""Persistence adapter for the Business module.

Owns the ``operating_hours`` table and assembles the read-only business profile from
other modules' tables (tenant, branches, menu appearance, staff) — a deliberate
cross-cutting read, mirroring the reports module. It never writes those tables.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.business.domain.entities import (
    BranchProfile,
    BusinessProfile,
    OperatingHours,
)
from restaurante.modules.business.infrastructure.models import OperatingHoursModel
from restaurante.modules.menu.infrastructure.models import MenuAppearanceModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.tenancy.models import BranchModel, TenantModel


def _hours(m: OperatingHoursModel) -> OperatingHours:
    return OperatingHours(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        weekday=m.weekday,
        open_minute=m.open_minute,
        close_minute=m.close_minute,
    )


class SqlAlchemyBusinessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def primary_branch_id(self, tenant_id: uuid.UUID) -> uuid.UUID | None:
        stmt = (
            select(BranchModel.id)
            .where(BranchModel.tenant_id == tenant_id, BranchModel.is_primary.is_(True))
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalars().first()

    async def list_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[OperatingHours]:
        stmt = (
            select(OperatingHoursModel)
            .where(
                OperatingHoursModel.tenant_id == tenant_id,
                OperatingHoursModel.branch_id == branch_id,
            )
            .order_by(
                OperatingHoursModel.weekday, OperatingHoursModel.open_minute
            )
        )
        return [_hours(m) for m in (await self._session.execute(stmt)).scalars()]

    async def replace_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, hours: list[OperatingHours]
    ) -> list[OperatingHours]:
        """Full replace: drop the branch's windows, insert the new set, in one transaction."""
        await self._session.execute(
            sql_delete(OperatingHoursModel).where(
                OperatingHoursModel.tenant_id == tenant_id,
                OperatingHoursModel.branch_id == branch_id,
            )
        )
        for h in hours:
            self._session.add(
                OperatingHoursModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    weekday=h.weekday,
                    open_minute=h.open_minute,
                    close_minute=h.close_minute,
                )
            )
        await self._session.commit()
        return await self.list_hours(tenant_id, branch_id)

    async def update_tenant_identity(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str,
        tax_id: str | None,
        email: str | None,
        phone: str | None,
    ) -> None:
        await self._session.execute(
            sql_update(TenantModel)
            .where(TenantModel.id == tenant_id)
            .values(name=name, tax_id=tax_id, email=email, phone=phone)
        )
        await self._session.commit()

    async def update_branch_details(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        address: str | None,
        phone: str | None,
        name: str | None = None,
    ) -> bool:
        if not await self.branch_exists(tenant_id, branch_id):
            return False
        # `name` sólo se toca cuando viene: una sucursal sin nombre no existe, así que un
        # payload que lo omite tiene que dejar el que había, no vaciarlo.
        values: dict[str, str | None] = {"address": address, "phone": phone}
        if name is not None:
            values["name"] = name
        await self._session.execute(
            sql_update(BranchModel)
            .where(BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id)
            .values(**values)
        )
        await self._session.commit()
        return True

    async def _appearance_brand(self, tenant_id: uuid.UUID) -> dict[str, Any]:
        stmt = select(MenuAppearanceModel.config).where(
            MenuAppearanceModel.tenant_id == tenant_id
        )
        config = (await self._session.execute(stmt)).scalar_one_or_none()
        brand = (config or {}).get("brand", {}) if isinstance(config, dict) else {}
        return brand if isinstance(brand, dict) else {}

    async def get_profile(self, tenant_id: uuid.UUID) -> BusinessProfile:
        tenant = (
            await self._session.execute(
                select(TenantModel).where(TenantModel.id == tenant_id)
            )
        ).scalar_one()

        branch_rows = (
            await self._session.execute(
                select(BranchModel)
                .where(BranchModel.tenant_id == tenant_id)
                .order_by(BranchModel.is_primary.desc(), BranchModel.name)
            )
        ).scalars().all()

        all_hours = (
            await self._session.execute(
                select(OperatingHoursModel)
                .where(OperatingHoursModel.tenant_id == tenant_id)
                .order_by(
                    OperatingHoursModel.weekday, OperatingHoursModel.open_minute
                )
            )
        ).scalars().all()
        hours_by_branch: dict[uuid.UUID, list[OperatingHours]] = {}
        for m in all_hours:
            hours_by_branch.setdefault(m.branch_id, []).append(_hours(m))

        staff_count = (
            await self._session.execute(
                select(func.count(EmployeeModel.id)).where(
                    EmployeeModel.tenant_id == tenant_id
                )
            )
        ).scalar_one()

        brand = await self._appearance_brand(tenant_id)
        return BusinessProfile(
            tenant_id=tenant.id,
            name=tenant.name,
            tax_id=tenant.tax_id,
            email=tenant.email,
            phone=tenant.phone,
            photo_url=brand.get("logoUrl") or None,
            banner_url=brand.get("bannerUrl") or None,
            payment_qr_url=brand.get("paymentQrUrl") or None,
            staff_count=int(staff_count),
            branches=[
                BranchProfile(
                    id=b.id,
                    name=b.name,
                    address=b.address,
                    phone=b.phone,
                    is_primary=b.is_primary,
                    hours=hours_by_branch.get(b.id, []),
                )
                for b in branch_rows
            ],
        )
