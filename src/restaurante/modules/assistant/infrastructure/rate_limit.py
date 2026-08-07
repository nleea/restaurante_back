"""El límite por minuto, sobre la caché que ya existe.

Es DEFENSIVO, no una frontera de seguridad, y por eso se dice en voz alta lo que no hace: el
puerto `Cache` sólo tiene `get`/`set`, así que entre leer y escribir caben dos llamadas
simultáneas y alguna vez pasará una de más. No importa. Lo que este límite tiene que impedir
es un BUCLE —cientos de llamadas en un minuto—, y para eso una carrera ocasional es ruido;
lo que acota el gasto de una llamada suelta es el techo por llamada del plan, no esto.

La ventana es el minuto del reloj, no una ventana deslizante: dos claves distintas para dos
minutos distintos, cada una con su TTL, y nada que limpiar.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from restaurante.shared.cache.base import Cache

#: Se guarda algo más de dos minutos para que la clave del minuto en curso no expire mientras
#: sigue en uso. Sobra memoria, no lógica.
_TTL_SECONDS = 130


class CacheRateLimiter:
    def __init__(self, cache: Cache) -> None:
        self._cache = cache

    async def hit(self, tenant_id: uuid.UUID, limit_per_minute: int) -> bool:
        """`True` si esta llamada cabe en el minuto en curso."""
        if limit_per_minute <= 0:
            return True
        key = f"assistant:rate:{tenant_id}:{datetime.now(UTC):%Y%m%d%H%M}"
        raw = await self._cache.get(key)
        used = int(raw) if raw and raw.isdigit() else 0
        if used >= limit_per_minute:
            return False
        await self._cache.set(key, str(used + 1), ttl_seconds=_TTL_SECONDS)
        return True
