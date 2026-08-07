"""La etiqueta corta de un pedido: UNA derivación, tres consumidores.

Existe por un fallo concreto: el cliente leía `C328A1B2` en su WhatsApp y `c328a1b2-4f5e-…` en la
pantalla de confirmación, para el mismo pedido. Eran dos derivaciones distintas del mismo id, y una
de ellas no derivaba nada.
"""

from __future__ import annotations

import uuid

from restaurante.modules.delivery.infrastructure.repositories import _order_code
from restaurante.modules.messaging.application.use_cases.autoreply import order_number
from restaurante.shared.domain.order_label import order_label


def test_the_label_is_short_and_readable_out_loud() -> None:
    order_id = uuid.UUID("c328a1b2-4f5e-4a3b-9c1d-000000000000")
    assert order_label(order_id) == "C328A1B2"


def test_every_consumer_says_the_same_number() -> None:
    """El chat, el mostrador y el tiquete tienen que estar diciendo lo mismo."""
    order_id = uuid.uuid4()
    assert order_label(order_id) == order_number(order_id) == _order_code(order_id)


def test_it_is_a_label_and_not_an_identifier() -> None:
    """Ocho caracteres no identifican: para eso está el uuid. Sirven para leerlos por teléfono."""
    order_id = uuid.uuid4()
    label = order_label(order_id)
    assert len(label) == 8
    assert label == label.upper()
