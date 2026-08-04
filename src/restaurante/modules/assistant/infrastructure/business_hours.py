"""El adaptador de horarios: `OpeningHoursReader` sobre el módulo `business`.

Vive aquí y no en la aplicación por lo mismo que el canal de WhatsApp: la flecha SALE. El
asistente declara qué necesita saber —si hay alguien detrás— y la raíz de composición decide
quién se lo contesta.

Una regla que no está en `business` y sí tiene que estar aquí: **un horario sin configurar no
es un horario cerrado**. Un negocio recién dado de alta no tiene ventanas, y tomar eso por
"cerrado" dejaría a su asistente mudo para siempre el mismo día que lo enciende — un fallo que
además se leería como que el producto no funciona.
"""

from __future__ import annotations

import uuid

from restaurante.modules.business.application.clock import weekday_and_minute
from restaurante.modules.business.application.use_cases.manage_business import (
    BusinessService,
)


class BusinessOpeningHours:
    def __init__(self, business: BusinessService) -> None:
        self._business = business

    async def status(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> tuple[bool, tuple[int, int] | None]:
        # Hora LOCAL de la sede: `datetime.now()` en un contenedor es UTC, y con eso el
        # asistente se declararía cerrado a media tarde en Colombia.
        weekday, minute = weekday_and_minute()
        open_now, next_opening, windows = await self._business.storefront_status(
            tenant_id, weekday=weekday, minute=minute, branch_id=branch_id
        )
        if not windows:
            return True, None
        return open_now, next_opening
