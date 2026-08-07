"""El código que va impreso en la calcomanía del QR de una mesa.

No es un identificador —para eso está el uuid— ni un secreto. Está pegado con adhesivo a una
mesa, a la vista de cualquiera que entre, y no rota: un código rotatorio obligaría a reimprimir
diez calcomanías cada vez, y un negocio que no reimprime a tiempo se queda sin poder vender en
salón. Lo que de verdad acota pedir a la mesa 5 desde la calle es dinámico y vive en otra parte:
la caja abierta, el horario abierto, y que la mesa sea un sitio físico donde alguien va a tener
que pagar antes de irse.

El alfabeto excluye `0/O` y `1/I/L` porque quien no pueda escanear va a teclear lo que lee, y a
esa persona la separan de su almuerzo seis caracteres.

Seis caracteres sobre 31 símbolos son ~887 millones de combinaciones. La unicidad es **por
sede**, no global: la sede va en la ruta del QR, así que dos sucursales pueden repetir un código
sin que ninguna calcomanía se vuelva ambigua.
"""

from __future__ import annotations

import secrets
from collections.abc import Callable, Container

ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"
LENGTH = 6

# Cuántas veces se reintenta ante colisión antes de rendirse. Con ~887 millones de códigos y
# diez mesas por sede, llegar a agotarlo significa que el generador está roto, no que hubo mala
# suerte: fallar ruidosamente es mejor que girar para siempre.
MAX_ATTEMPTS = 12


class TableCodeExhaustedError(RuntimeError):
    """No se pudo acuñar un código libre. Señal de generador roto, no de mala suerte."""


def generate_table_code(rng: Callable[[str], str] = secrets.choice) -> str:
    """Un código suelto. `rng` se inyecta para poder fijarlo en los tests."""
    return "".join(rng(ALPHABET) for _ in range(LENGTH))


def mint_table_code(
    taken: Container[str],
    rng: Callable[[str], str] = secrets.choice,
) -> str:
    """Un código que no está en `taken` (los códigos ya usados EN ESA SEDE).

    El reintento es cortesía para dar un código bueno a la primera; la garantía de verdad es el
    índice único `(branch_id, code)` de la base, porque dos peticiones concurrentes pueden leer
    el mismo `taken` y acuñar el mismo código.
    """
    for _ in range(MAX_ATTEMPTS):
        code = generate_table_code(rng)
        if code not in taken:
            return code
    raise TableCodeExhaustedError(
        f"No se pudo acuñar un código de mesa libre en {MAX_ATTEMPTS} intentos."
    )
