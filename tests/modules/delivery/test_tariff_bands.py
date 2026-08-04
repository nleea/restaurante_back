"""Las reglas de la escalera de precios: qué plan se acepta y qué banda cobra.

Lo que se protege es una escalera CONTINUA. Un plan con un hueco o desordenado no falla ruidoso:
selecciona la banda equivocada, cobra de menos durante semanas, y se descubre cuadrando caja.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from restaurante.modules.delivery.application.pricing import select_tariff_band
from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    DeliveryService,
)
from restaurante.modules.delivery.domain.entities import DeliveryTariffBand
from restaurante.shared.domain.errors import ValidationError

TENANT = uuid.uuid4()
BRANCH = uuid.uuid4()


def _band(max_km: str, fee: str, position: int) -> DeliveryTariffBand:
    return DeliveryTariffBand(
        tenant_id=TENANT,
        branch_id=BRANCH,
        max_distance_km=Decimal(max_km),
        fee=Decimal(fee),
        position=position,
    )


PLAN = [_band("2", "3000", 0), _band("4", "5000", 1), _band("6", "7000", 2)]


class TestSelectingTheBand:
    def test_the_first_band_that_covers_the_distance_wins(self) -> None:
        assert select_tariff_band(Decimal("1.5"), PLAN) == PLAN[0]
        assert select_tariff_band(Decimal("3.2"), PLAN) == PLAN[1]
        assert select_tariff_band(Decimal("5.9"), PLAN) == PLAN[2]

    def test_a_bands_own_limit_belongs_to_that_band(self) -> None:
        """Inclusiva por arriba: 2,000 km paga la banda de 2 km, no la siguiente."""
        assert select_tariff_band(Decimal("2"), PLAN) == PLAN[0]
        assert select_tariff_band(Decimal("4"), PLAN) == PLAN[1]

    def test_beyond_the_last_band_nobody_charges(self) -> None:
        """Eso es fuera de cobertura: sin tarifa, no una tarifa de cero."""
        assert select_tariff_band(Decimal("6.001"), PLAN) is None

    def test_zero_distance_still_pays_the_first_band(self) -> None:
        """El cliente de al lado paga domicilio: la primera banda empieza en cero."""
        assert select_tariff_band(Decimal("0"), PLAN) == PLAN[0]

    def test_selection_follows_position_not_list_order(self) -> None:
        """La posición es la que ordena la escalera; el orden en que lleguen las filas no.

        Sin esto, un repositorio que devolviera las bandas en otro orden cobraría la tarifa
        equivocada sin fallar en ningún sitio.
        """
        shuffled = [PLAN[2], PLAN[0], PLAN[1]]
        assert select_tariff_band(Decimal("1.5"), shuffled) == PLAN[0]

    def test_no_plan_charges_nothing(self) -> None:
        assert select_tariff_band(Decimal("1"), []) is None


class FakeRepo:
    """Sólo lo que la validación del plan toca."""

    def __init__(self) -> None:
        self.saved: list[DeliveryTariffBand] | None = None

    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        return True

    async def replace_tariff_bands(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, bands: list[DeliveryTariffBand]
    ) -> list[DeliveryTariffBand]:
        self.saved = bands
        return bands


def _service(repo: FakeRepo) -> DeliveryService:
    return DeliveryService(repo)  # type: ignore[arg-type]


class TestSavingAPlan:
    @pytest.mark.asyncio
    async def test_a_continuous_increasing_plan_is_saved_with_its_positions(self) -> None:
        repo = FakeRepo()

        await _service(repo).replace_tariff_bands(
            TENANT,
            BRANCH,
            [
                {"max_distance_km": "2", "fee": "3000"},
                {"max_distance_km": "4", "fee": "5000"},
            ],
        )

        assert repo.saved is not None
        # La posición se deriva del orden enviado: es lo que hace la escalera reproducible.
        assert [b.position for b in repo.saved] == [0, 1]
        assert [b.max_distance_km for b in repo.saved] == [Decimal("2"), Decimal("4")]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("bands", "why"),
        [
            ([], "un plan vacío no cotiza nada"),
            ([{"max_distance_km": "0", "fee": "3000"}], "una banda de cero km no cubre nada"),
            ([{"max_distance_km": "-1", "fee": "3000"}], "una distancia negativa"),
            ([{"max_distance_km": "2", "fee": "-1"}], "una tarifa negativa"),
            (
                [
                    {"max_distance_km": "4", "fee": "3000"},
                    {"max_distance_km": "2", "fee": "5000"},
                ],
                "distancias que no crecen: la selección cobraría la banda equivocada",
            ),
            (
                [
                    {"max_distance_km": "2", "fee": "3000"},
                    {"max_distance_km": "2", "fee": "5000"},
                ],
                "una distancia repetida: dos tarifas para el mismo kilómetro",
            ),
        ],
    )
    async def test_an_invalid_plan_is_refused(
        self, bands: list[dict[str, str]], why: str
    ) -> None:
        repo = FakeRepo()

        with pytest.raises(ValidationError):
            await _service(repo).replace_tariff_bands(TENANT, BRANCH, bands)

        # Y el plan ANTERIOR sobrevive: un guardado rechazado no puede dejar la sede sin tarifas.
        assert repo.saved is None, why

    @pytest.mark.asyncio
    async def test_a_free_delivery_band_is_valid(self) -> None:
        """Cero no es un error: regalar el domicilio cerca es una decisión comercial."""
        repo = FakeRepo()

        await _service(repo).replace_tariff_bands(
            TENANT, BRANCH, [{"max_distance_km": "1", "fee": "0"}]
        )

        assert repo.saved is not None
        assert repo.saved[0].fee == Decimal("0")
