"""Application service for the Business module: operating hours + business profile."""

from __future__ import annotations

import uuid

from restaurante.modules.business.domain.entities import (
    BranchDetailsUpdate,
    BusinessProfile,
    OperatingHours,
)
from restaurante.modules.business.domain.hours import (
    MINUTES_PER_DAY,
    HoursWindow,
    is_open_at,
    next_opening,
)
from restaurante.modules.business.domain.ports import BusinessRepository
from restaurante.modules.menu.application.use_cases.manage_appearance import (
    AppearanceService,
)
from restaurante.shared.domain.errors import NotFoundError, ValidationError

_DAYS = 7


class BusinessService:
    def __init__(
        self, repo: BusinessRepository, appearance: AppearanceService | None = None
    ) -> None:
        self._repo = repo
        # Optional: when wired, the profile's photo is written to the shared appearance
        # `brand.logoUrl` (the value the storefront reads), single-sourcing the identity photo.
        self._appearance = appearance

    async def _require_branch(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> None:
        if not await self._repo.branch_exists(tenant_id, branch_id):
            raise NotFoundError(f"Sucursal no encontrada: {branch_id}")

    async def get_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[OperatingHours]:
        await self._require_branch(tenant_id, branch_id)
        return await self._repo.list_hours(tenant_id, branch_id)

    async def set_hours(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, hours: list[OperatingHours]
    ) -> list[OperatingHours]:
        await self._require_branch(tenant_id, branch_id)
        for h in hours:
            if not 0 <= h.weekday < _DAYS:
                raise ValidationError(f"Día de la semana inválido: {h.weekday}")
            if not 0 <= h.open_minute < MINUTES_PER_DAY:
                raise ValidationError(f"Hora de apertura inválida: {h.open_minute}")
            if not 0 < h.close_minute <= MINUTES_PER_DAY:
                raise ValidationError(f"Hora de cierre inválida: {h.close_minute}")
        return await self._repo.replace_hours(tenant_id, branch_id, hours)

    async def get_profile(self, tenant_id: uuid.UUID) -> BusinessProfile:
        return await self._repo.get_profile(tenant_id)

    async def update_profile(
        self,
        tenant_id: uuid.UUID,
        *,
        name: str,
        tax_id: str | None,
        email: str | None,
        phone: str | None,
        branches: list[BranchDetailsUpdate],
        photo_url: str | None = None,
        payment_qr_url: str | None = None,
    ) -> BusinessProfile:
        """Edit tenant identity, branch details and (optionally) the photo; return the profile."""
        if not name.strip():
            raise ValidationError("El nombre del negocio es obligatorio.")
        await self._repo.update_tenant_identity(
            tenant_id, name=name.strip(), tax_id=tax_id, email=email, phone=phone
        )
        for b in branches:
            branch_name = b.name.strip() if b.name is not None else None
            if branch_name == "":
                raise ValidationError("El nombre de la sucursal es obligatorio.")
            ok = await self._repo.update_branch_details(
                tenant_id, b.id, address=b.address, phone=b.phone, name=branch_name
            )
            if not ok:
                raise NotFoundError(f"Sucursal no encontrada: {b.id}")
        if (
            photo_url is not None or payment_qr_url is not None
        ) and self._appearance is not None:
            # Single-source the images: they live in the shared appearance brand, which is also
            # what the public carta reads — así el QR llega al checkout sin endpoint nuevo.
            config = await self._appearance.get_appearance(tenant_id)
            brand = config.setdefault("brand", {})
            if photo_url is not None:
                brand["logoUrl"] = photo_url
            if payment_qr_url is not None:
                brand["paymentQrUrl"] = payment_qr_url
            await self._appearance.save_appearance(tenant_id, config)
        return await self._repo.get_profile(tenant_id)

    async def branch_status(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        weekday: int,
        minute: int,
    ) -> tuple[bool, tuple[int, int] | None]:
        """(is within opening hours now, next opening (weekday, minute) or None)."""
        hours = await self._repo.list_hours(tenant_id, branch_id)
        windows = [
            HoursWindow(h.weekday, h.open_minute, h.close_minute) for h in hours
        ]
        open_now = is_open_at(windows, weekday, minute)
        return open_now, next_opening(windows, weekday, minute)

    async def storefront_status(
        self,
        tenant_id: uuid.UUID,
        *,
        weekday: int,
        minute: int,
        branch_id: uuid.UUID | None = None,
    ) -> tuple[bool, tuple[int, int] | None, list[OperatingHours]]:
        """Public storefront view: a branch's open-now, next-opening, and windows.

        ``branch_id`` addresses a specific branch (the public storefront is branch-scoped);
        omitting it falls back to the tenant's primary branch for the code-less endpoints.

        With no branch or no configured hours, reports closed with no next opening
        and an empty window list — the storefront falls back to a generic closed message.
        """
        if branch_id is None:
            branch_id = await self._repo.primary_branch_id(tenant_id)
        if branch_id is None:
            return False, None, []
        hours = await self._repo.list_hours(tenant_id, branch_id)
        windows = [
            HoursWindow(h.weekday, h.open_minute, h.close_minute) for h in hours
        ]
        return is_open_at(windows, weekday, minute), next_opening(
            windows, weekday, minute
        ), hours
