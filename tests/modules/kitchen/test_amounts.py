"""Cómo se lee una cantidad en el pase.

La receta guarda `0.150 kg` porque el inventario se lleva en kilos; el cocinero lee `150 g`. El
umbral vive en una sola función y estos tests son los que lo fijan.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from restaurante.modules.kitchen.domain.amounts import SubUnit, format_amount

GRAMS = SubUnit(abbreviation="g", conversion_factor=Decimal("0.001"))


@pytest.mark.parametrize(
    ("quantity", "expected"),
    [
        # Por debajo de 1 baja a gramos: es la razón de existir de la función.
        ("0.150", "150 g"),
        ("0.015", "15 g"),
        ("0.0005", "0.5 g"),
        # Exactamente 1 se queda: el umbral es estricto y aquí es donde se ve.
        ("1", "1 kg"),
        ("1.500", "1.5 kg"),
        ("25", "25 kg"),
    ],
)
def test_the_threshold_decides_the_unit(quantity: str, expected: str) -> None:
    assert format_amount(Decimal(quantity), "kg", GRAMS) == expected


def test_without_a_sub_unit_the_amount_stays_in_its_own() -> None:
    """`und` no tiene unidad menor, y media unidad sigue siendo media unidad."""
    assert format_amount(Decimal("1.000"), "und") == "1 und"
    assert format_amount(Decimal("0.500"), "und") == "0.5 und"


def test_scale_zeros_are_dropped() -> None:
    """La columna tiene tres decimales por su escala, no porque el pase los necesite."""
    assert format_amount(Decimal("300.000"), "g") == "300 g"
    assert format_amount(Decimal("2.000"), "L") == "2 L"


def test_a_real_decimal_survives() -> None:
    assert format_amount(Decimal("1.250"), "kg", GRAMS) == "1.25 kg"


def test_large_multiples_of_ten_are_not_scientific_notation() -> None:
    """`normalize()` devolvería `3E+2`, que en una comanda no significa nada."""
    assert format_amount(Decimal("300.000"), "kg", GRAMS) == "300 kg"
    assert format_amount(Decimal("1000"), "g") == "1000 g"


def test_a_zero_factor_never_divides() -> None:
    """Un dato de conversión corrupto degrada a la unidad propia, no revienta el pase."""
    broken = SubUnit(abbreviation="g", conversion_factor=Decimal("0"))
    assert format_amount(Decimal("0.150"), "kg", broken) == "0.15 kg"
