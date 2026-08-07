"""Cómo se lee una cantidad en el pase.

La receta guarda `0.150 kg` porque el inventario se lleva en kilos. Nadie pesa 0.15 kg de carne:
el cocinero lee 150 g. Esta es la única traducción entre las dos formas de decir lo mismo.

Sin tabla de conversiones en el código: `units_of_measure` ya modela la familia con
`base_unit_id` y `conversion_factor`, y quemarla aquí la duplicaría y se rompería con la primera
unidad que alguien añada.

Función pura, sin ORM: vive en el dominio porque es una regla de presentación del negocio, no un
detalle de persistencia.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#: Por debajo de esta cantidad se baja a la sub-unidad. Es donde el número deja de tener ceros a
#: la izquierda que nadie pesa: `1500 g` no se lee mejor que `1.5 kg`, pero `150 g` sí es mejor
#: que `0.15 kg`.
_SUBUNIT_THRESHOLD = Decimal(1)


@dataclass(frozen=True)
class SubUnit:
    """La unidad menor de una familia: `g` para `kg`, con cuántos kg vale un gramo."""

    abbreviation: str
    #: Cuánto de la unidad padre vale UNA de ésta (`g` → `0.001`).
    conversion_factor: Decimal


def format_amount(
    quantity: Decimal, unit_abbr: str, sub_unit: SubUnit | None = None
) -> str:
    """`0.150` + `kg` + `g(0.001)` → `"150 g"`; `1.500` + `kg` → `"1.5 kg"`.

    Sin sub-unidad —`und`, o una familia sin unidad menor— la cantidad se queda en la suya.
    Los ceros de escala se recortan siempre: la columna tiene tres decimales por su escala, no
    porque el pase necesite esa precisión.
    """
    if (
        sub_unit is not None
        and quantity < _SUBUNIT_THRESHOLD
        and sub_unit.conversion_factor > 0
    ):
        return f"{_trim(quantity / sub_unit.conversion_factor)} {sub_unit.abbreviation}"
    return f"{_trim(quantity)} {unit_abbr}".strip()


def _trim(value: Decimal) -> str:
    """`Decimal("300.000")` → `"300"`; `Decimal("1.500")` → `"1.5"`.

    `:f` en vez de `normalize()`: éste devuelve notación científica con los múltiplos de diez
    (`3E+2`), que en una comanda no significa nada.
    """
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
