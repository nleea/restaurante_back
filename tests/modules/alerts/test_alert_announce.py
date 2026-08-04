"""El anuncio desde el movimiento de stock.

La propiedad que se prueba es una sola y es la que sostiene todo el patrón: **un movimiento
de inventario no puede fallar porque la cola no esté.** El anuncio es el acelerador; el
registro del trabajo es el barrido.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from restaurante.modules.alerts.infrastructure.alert_queue import NullAlertQueue
from restaurante.modules.inventory.application.use_cases.manage_inventory import (
    ALERT_RULE_LOW_STOCK,
    InventoryService,
)

pytestmark = pytest.mark.asyncio


class RecordingAnnouncer:
    def __init__(self, *, fail: bool = False) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail = fail

    async def announce(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        rule_key: str,
        subject_ref: str,
    ) -> None:
        if self.fail:
            raise RuntimeError("Redis no está")
        self.calls.append((rule_key, subject_ref))


class FakeRepo:
    """Lo mínimo de `InventoryRepository` que toca `register_movement`."""

    def __init__(self) -> None:
        self.applied: list[object] = []

    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        return True

    async def ingredient_exists(
        self, tenant_id: uuid.UUID, ingredient_id: uuid.UUID
    ) -> bool:
        return True

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        return True

    async def apply_movement(self, movement: object, delta: Decimal) -> object:
        self.applied.append(movement)
        return movement


async def _move(service: InventoryService, ingredient_id: uuid.UUID) -> None:
    await service.register_movement(
        tenant_id=uuid.uuid4(),
        branch_id=uuid.uuid4(),
        ingredient_id=ingredient_id,
        employee_id=uuid.uuid4(),
        movement_type="in",
        quantity=Decimal("5"),
        reason="compra",
    )


async def test_a_movement_announces_the_ingredient() -> None:
    announcer = RecordingAnnouncer()
    service = InventoryService(repo=FakeRepo(), alerts=announcer)  # type: ignore[arg-type]
    ingredient_id = uuid.uuid4()

    await _move(service, ingredient_id)

    # El sujeto es el insumo, igual que en la regla: así el job mira sólo lo que se movió.
    assert announcer.calls == [(ALERT_RULE_LOW_STOCK, str(ingredient_id))]


async def test_a_dead_queue_does_not_fail_the_movement() -> None:
    """LA propiedad. Un Redis caído no puede impedir registrar una entrada de mercancía."""
    repo = FakeRepo()
    service = InventoryService(repo=repo, alerts=RecordingAnnouncer(fail=True))  # type: ignore[arg-type]

    await _move(service, uuid.uuid4())

    # El movimiento se aplicó igual: lo que se pierde es la latencia, no el hecho.
    assert len(repo.applied) == 1


async def test_inventory_works_with_no_announcer_at_all() -> None:
    repo = FakeRepo()
    service = InventoryService(repo=repo)  # type: ignore[arg-type]

    await _move(service, uuid.uuid4())

    assert len(repo.applied) == 1


async def test_the_null_announcer_is_a_no_op() -> None:
    """Su existencia es la prueba de que el camino del job es opcional de verdad."""
    repo = FakeRepo()
    service = InventoryService(repo=repo, alerts=NullAlertQueue())  # type: ignore[arg-type]

    await _move(service, uuid.uuid4())

    assert len(repo.applied) == 1
