"""Anunciar que un sujeto merece una mirada. El acelerador, no el registro del trabajo.

Copiado de `delivery/infrastructure/geocode_queue.py`, incluida la razón por la que **todo
aquí falla en silencio**: un movimiento de stock no puede fallar porque Redis no esté. Y
tragarse el error sólo es seguro porque el barrido sigue ahí para encontrar lo que se cayó.

Un anuncio perdido es una regresión de latencia —la alerta llega en el próximo barrido en
vez de en segundos—, nunca una alerta perdida.

`arq` se importa perezosamente, igual que `RedisCache` hace con `redis`, para que el módulo
importe y la suite corra sin broker.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import uuid
from typing import Any

from restaurante.modules.alerts.infrastructure.worker import (
    ALERTS_QUEUE,
    EVALUATE_SUBJECT_JOB,
)

# Sin reintentos de conexión y con techo de espera: fallar el anuncio es gratis, y hacer
# esperar cinco segundos a quien registra una salida de inventario contra un Redis muerto
# sería exactamente lo que este patrón existe para no hacer.
_CONN_RETRIES = 0
_ANNOUNCE_TIMEOUT_SECONDS = 2.0

_log = logging.getLogger(__name__)


class ArqAlertQueue:
    """Anuncia sobre `REDIS_URL`. Un pool perezoso por proceso."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._pool: Any | None = None

    async def _get_pool(self) -> Any:
        if self._pool is None:
            arq_connections = importlib.import_module("arq.connections")
            settings = arq_connections.RedisSettings.from_dsn(self._redis_url)
            settings.conn_retries = _CONN_RETRIES
            # Tiene que coincidir con el `queue_name` del worker.
            self._pool = await arq_connections.create_pool(
                settings, default_queue_name=ALERTS_QUEUE
            )
        return self._pool

    async def announce(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject_ref: str,
    ) -> None:
        """Pide evaluar este sujeto ya. **Nunca levanta.**"""
        try:
            async with asyncio.timeout(_ANNOUNCE_TIMEOUT_SECONDS):
                pool = await self._get_pool()
                await pool.enqueue_job(
                    EVALUATE_SUBJECT_JOB,
                    str(tenant_id),
                    str(branch_id),
                    rule_key,
                    subject_ref,
                )
        except Exception:  # noqa: BLE001 - un anuncio nunca puede fallarle a quien lo hace
            # Warning y no exception: el barrido cubre esto, y una caída de Redis escribiría
            # si no una traza por cada movimiento de inventario del día.
            _log.warning(
                "No se pudo anunciar %s/%s para evaluar; lo cogerá el barrido.",
                rule_key,
                subject_ref,
                exc_info=True,
            )


class NullAlertQueue:
    """Sin cola. El sistema sigue siendo correcto: sólo pierde la latencia.

    Es la implementación por defecto cuando no hay Redis, y su existencia es la prueba
    práctica de la postura del diseño — el camino del job es opcional de verdad.
    """

    async def announce(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject_ref: str,
    ) -> None:
        return None
