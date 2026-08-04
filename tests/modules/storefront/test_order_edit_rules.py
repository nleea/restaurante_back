"""Las cuatro reglas de la edición, sin base de datos.

Son funciones puras a propósito, así que aquí no hay fixtures ni HTTP: hechos entran, veredicto
sale. Lo que se fija en estas pruebas es el *porqué* de cada regla, que es lo que un refactor
descuidado se lleva por delante sin que nada más se entere.
"""

from __future__ import annotations

from decimal import Decimal

from restaurante.modules.storefront.domain.order_edit import (
    REFUSAL_ITEM_STARTED,
    REFUSAL_ORDER_CLOSED,
    REFUSAL_OUT_OF_REACH,
    REFUSAL_PAID_LINE,
    REFUSAL_TOTAL_WOULD_DROP,
    OrderFacts,
    item_window,
    order_window,
    paid_line_change,
    total_invariant,
)


def _order(**over: object) -> OrderFacts:
    base: dict[str, object] = {
        "status": "open",
        "kitchen_state": "in_kitchen",
        "delivery_status": None,
        "total": Decimal("20000"),
        "paid": Decimal("0"),
    }
    base.update(over)
    return OrderFacts(**base)  # type: ignore[arg-type]


# --- La ventana del pedido ----------------------------------------------------------------
def test_a_delivery_still_at_the_pass_is_editable() -> None:
    """Listo NO es el techo de un domicilio: la bolsa sigue en el local.

    Es la diferencia entre una bolsa en el pase —donde el cocinero todavía puede hacer una
    cosa más y el domiciliario espera dos minutos— y una bolsa en la moto.
    """
    assert order_window(_order(kitchen_state="ready", delivery_status="pending")) is None
    assert order_window(_order(kitchen_state="ready", delivery_status="assigned")) is None


def test_once_the_motorbike_leaves_nothing_changes() -> None:
    for status in ("in_transit", "delivered", "not_delivered"):
        assert order_window(_order(delivery_status=status)) is REFUSAL_OUT_OF_REACH


def test_a_pickup_order_closes_when_it_is_ready() -> None:
    """Sin entrega no hay "salir": la comida espera en el mostrador."""
    assert order_window(_order(kitchen_state="ready")) is REFUSAL_OUT_OF_REACH
    assert order_window(_order(kitchen_state="in_kitchen")) is None


def test_a_closed_order_is_never_editable() -> None:
    assert order_window(_order(status="closed")) is REFUSAL_ORDER_CLOSED
    assert order_window(_order(status="cancelled")) is REFUSAL_ORDER_CLOSED


# --- La ventana del ítem ------------------------------------------------------------------
def test_an_item_nobody_started_is_editable() -> None:
    assert item_window(["pending", "pending"]) is None


def test_an_item_with_one_station_started_is_not() -> None:
    """Basta UNA estación: si la plancha ya empezó, el plato ya no es el que se pidió."""
    assert item_window(["pending", "in_progress"]) is REFUSAL_ITEM_STARTED
    assert item_window(["ready"]) is REFUSAL_ITEM_STARTED


def test_an_item_not_yet_sent_to_the_kitchen_is_editable() -> None:
    """Sin tickets no hay nada empezado — es el caso más común de todos."""
    assert item_window([]) is None


# --- La invariante del total --------------------------------------------------------------
def test_the_total_may_stay_the_same() -> None:
    """Una gaseosa negra por una roja: mismo precio, cambio válido.

    No hay ninguna regla que diga "del mismo precio": cae sola de la invariante.
    """
    assert total_invariant(Decimal("20000"), Decimal("20000")) is None


def test_the_total_may_go_up() -> None:
    assert total_invariant(Decimal("20000"), Decimal("25000")) is None


def test_the_total_may_not_go_down() -> None:
    """Cambiar la gaseosa por agua, o quitar algo: eso lo resuelve una persona."""
    assert (
        total_invariant(Decimal("20000"), Decimal("18000")) is REFUSAL_TOTAL_WOULD_DROP
    )


# --- Las líneas pagadas -------------------------------------------------------------------
def test_a_paid_line_may_grow() -> None:
    """Queso extra sobre una hamburguesa ya pagada: sí. Lo pagado sigue donde estaba."""
    paid = _order(total=Decimal("20000"), paid=Decimal("20000"))
    assert paid_line_change(paid, changes_line_identity=False) is None


def test_a_paid_line_may_not_change_product() -> None:
    paid = _order(total=Decimal("20000"), paid=Decimal("20000"))
    assert paid_line_change(paid, changes_line_identity=True) is REFUSAL_PAID_LINE


def test_without_payment_the_product_may_change() -> None:
    assert paid_line_change(_order(), changes_line_identity=True) is None


def test_a_partial_payment_is_not_a_paid_order() -> None:
    """Un abono no congela nada: lo que congela es que lo recibido cubra el total."""
    partial = _order(total=Decimal("20000"), paid=Decimal("5000"))
    assert paid_line_change(partial, changes_line_identity=True) is None
