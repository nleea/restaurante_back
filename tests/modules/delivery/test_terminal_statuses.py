"""Una sola lista de estados terminales, y todos los que preguntan derivan de ella.

Este archivo existe por cómo se rompe esto. La lista estuvo copiada en tres sitios —el servicio de
delivery, el guard de cierre de caja y el histórico de sesión— y añadir un estado sin tocar los
tres deja el bloqueo puesto SIN causa visible: el síntoma es idéntico al bug que se acababa de
arreglar, así que se diagnostica dos veces.

Lo que se comprueba no es el contenido de la lista: es que nadie tenga la suya.
"""

from __future__ import annotations

import ast
import pathlib

from restaurante.modules.delivery.application.use_cases import manage_delivery
from restaurante.modules.delivery.domain.entities import (
    DELIVERY_CANCELLED,
    DELIVERY_DELIVERED,
    DELIVERY_NOT_DELIVERED,
    DELIVERY_PENDING,
    DELIVERY_TERMINAL_STATUSES,
    DELIVERY_UNRESOLVED_STATUSES,
)

# .../src/restaurante/modules/delivery/application/use_cases/manage_delivery.py → .../src
_SRC = pathlib.Path(manage_delivery.__file__).parents[5]

#: Los módulos que preguntan "¿está resuelta?" sobre la base de datos.
_CONSUMERS = (
    "restaurante/modules/cash/infrastructure/repositories.py",
    "restaurante/modules/reports/infrastructure/repositories.py",
)


def test_the_terminal_list_is_complete_and_disjoint_from_the_unresolved_one() -> None:
    """Un estado en las dos listas, o en ninguna, sería una entrega imposible de clasificar."""
    assert set(DELIVERY_TERMINAL_STATUSES).isdisjoint(DELIVERY_UNRESOLVED_STATUSES)
    every = set(DELIVERY_TERMINAL_STATUSES) | set(DELIVERY_UNRESOLVED_STATUSES)
    assert every == {
        DELIVERY_PENDING,
        "assigned",
        "in_transit",
        DELIVERY_DELIVERED,
        DELIVERY_NOT_DELIVERED,
        DELIVERY_CANCELLED,
    }


def test_the_delivery_service_does_not_keep_its_own_copy() -> None:
    assert manage_delivery.D_TERMINAL is DELIVERY_TERMINAL_STATUSES
    assert manage_delivery.D_UNRESOLVED is DELIVERY_UNRESOLVED_STATUSES


def test_no_consumer_hardcodes_the_terminal_states() -> None:
    """El que importa: un `notin_(("delivered", "not_delivered"))` escrito a mano.

    Se mira el ARCHIVO y no el comportamiento porque el fallo es de omisión: un consumidor con su
    propia lista da resultados correctos hasta el día que se añade un estado, y entonces bloquea
    una caja sin que nada apunte a él.
    """
    known = {
        DELIVERY_DELIVERED,
        DELIVERY_NOT_DELIVERED,
        DELIVERY_CANCELLED,
    }
    for relative in _CONSUMERS:
        path = _SRC / relative
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Tuple | ast.List | ast.Set):
                continue
            values = {
                el.value
                for el in node.elts
                if isinstance(el, ast.Constant) and isinstance(el.value, str)
            }
            # Dos o más estados juntos escritos a mano ES la lista copiada.
            assert len(values & known) < 2, (
                f"{relative} tiene su propia lista de estados terminales {values & known}; "
                "debe derivar de DELIVERY_TERMINAL_STATUSES o el próximo estado nuevo "
                "bloqueará una caja sin dejar rastro."
            )


def test_every_consumer_imports_the_single_definition() -> None:
    for relative in _CONSUMERS:
        source = (_SRC / relative).read_text()
        assert "DELIVERY_TERMINAL_STATUSES" in source, (
            f"{relative} no deriva de la definición única de estados terminales."
        )
