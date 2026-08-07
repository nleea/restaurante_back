"""Adapter for `storefront.DeliveryReadiness`: can this branch take a delivery order at all?

The failure this closes is silent, which is why it needs a gate and not a warning. With no
tariff bands (or no pin on the map) the chain still *runs* — the order is accepted, the customer
is thanked, the quote worker picks it up, finds nothing to price it with, and marks it
unquotable. Nobody is charged, nobody is messaged, and the customer waits for a link that will
never arrive. From the outside it looks exactly like a working restaurant that is slow.

Telling them "no estamos haciendo domicilios" at checkout is worse news delivered honestly, and
it is recoverable: they can still order for pickup.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.delivery.infrastructure.models import (
    DeliverySettingModel,
    DeliveryTariffBandModel,
)


class SqlAlchemyDeliveryReadiness:
    """Implements `storefront.DeliveryReadiness` over the branch's delivery config."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def can_take_deliveries(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        """True when this branch can actually put a price on a delivery.

        Two conditions, both structural: a pin to measure FROM, and at least one tariff band to
        measure INTO. Neither is about a particular order, which is why this can be answered
        before the customer finishes typing their address.
        """
        pinned = (
            await self._session.execute(
                select(DeliverySettingModel.id).where(
                    DeliverySettingModel.tenant_id == tenant_id,
                    DeliverySettingModel.branch_id == branch_id,
                    DeliverySettingModel.latitude.is_not(None),
                    DeliverySettingModel.longitude.is_not(None),
                )
            )
        ).scalar_one_or_none()
        if pinned is None:
            return False
        bands = (
            await self._session.execute(
                select(func.count(DeliveryTariffBandModel.id)).where(
                    DeliveryTariffBandModel.tenant_id == tenant_id,
                    DeliveryTariffBandModel.branch_id == branch_id,
                )
            )
        ).scalar_one()
        return bool(bands)
