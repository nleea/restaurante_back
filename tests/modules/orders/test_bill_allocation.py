"""El reparto en cascada, probado a mano y sin base de datos.

Es la aritmética que decide cuánto se registra sobre cada comanda cuando el cajero cobra una
mesa entera. Se prueba aquí, aislada, porque un fallo aquí no se ve: deja una comanda cerrada
sin cubrir o cobrada dos veces, y eso sólo aparece en el arqueo del turno.
"""

from __future__ import annotations

from decimal import Decimal

from restaurante.modules.orders.domain.bill_allocation import (
    BillMember,
    BillPayment,
    allocate,
)


def _m(order_id: str, owed: str) -> BillMember:
    return BillMember(order_id=order_id, outstanding=Decimal(owed))


def _p(amount: str, method: str = "cash") -> BillPayment:
    return BillPayment(amount=Decimal(amount), method=method)


ANA, LUIS, SOFIA = _m("ana", "32000"), _m("luis", "54000"), _m("sofia", "34000")


def test_one_payment_covers_the_whole_table() -> None:
    result = allocate([ANA, LUIS, SOFIA], [_p("120000")])

    assert [(a.order_id, a.amount) for a in result.allocations] == [
        ("ana", Decimal("32000")),
        ("luis", Decimal("54000")),
        ("sofia", Decimal("34000")),
    ]
    assert result.uncovered == 0
    assert result.change == 0


def test_two_methods_split_across_the_waterfall() -> None:
    """La comanda que queda a caballo lleva dos pagos — un caso que el sistema ya sabe manejar."""
    result = allocate([ANA, LUIS, SOFIA], [_p("80000", "card"), _p("40000", "cash")])

    assert [(a.order_id, a.amount, a.method) for a in result.allocations] == [
        ("ana", Decimal("32000"), "card"),
        ("luis", Decimal("48000"), "card"),
        ("luis", Decimal("6000"), "cash"),
        ("sofia", Decimal("34000"), "cash"),
    ]
    assert result.uncovered == 0


def test_a_partial_payment_leaves_the_rest_uncovered() -> None:
    """Cobrar de menos no puede parecer cobrado: quien llama tiene que poder negarse a cerrar."""
    result = allocate([ANA, LUIS, SOFIA], [_p("50000")])

    assert [(a.order_id, a.amount) for a in result.allocations] == [
        ("ana", Decimal("32000")),
        ("luis", Decimal("18000")),
    ]
    assert result.uncovered == Decimal("70000")  # 36.000 de Luis + 34.000 de Sofía


def test_overpayment_is_change_and_belongs_to_nobody() -> None:
    """El sobrante no se le cuelga a la última comanda: es dinero que vuelve al cliente."""
    result = allocate([ANA], [_p("50000")])

    assert [(a.order_id, a.amount) for a in result.allocations] == [
        ("ana", Decimal("32000"))
    ]
    assert result.uncovered == 0
    assert result.change == Decimal("18000")


def test_a_bill_of_one_is_not_a_special_case() -> None:
    """Separar la cuenta es el mismo mecanismo con un miembro, no otro camino."""
    result = allocate([LUIS], [_p("54000")])

    assert len(result.allocations) == 1
    assert result.uncovered == 0


def test_exact_payment_per_member_produces_one_allocation_each() -> None:
    result = allocate([ANA, LUIS], [_p("32000"), _p("54000")])

    assert [(a.order_id, a.amount) for a in result.allocations] == [
        ("ana", Decimal("32000")),
        ("luis", Decimal("54000")),
    ]
    assert result.change == 0


def test_decimals_are_not_rounded_away() -> None:
    """La cascada no reparte fracciones: cada asignación es un importe exacto de la comanda."""
    result = allocate(
        [_m("a", "10500.50"), _m("b", "9499.50")], [_p("20000.00")]
    )

    assert [a.amount for a in result.allocations] == [
        Decimal("10500.50"),
        Decimal("9499.50"),
    ]
    assert result.uncovered == 0
    assert result.change == 0


def test_a_member_that_owes_nothing_is_skipped() -> None:
    """Una comanda ya pagada (fiado resuelto aparte, por ejemplo) no consume del cobro."""
    result = allocate([_m("pagada", "0"), ANA], [_p("32000")])

    assert [(a.order_id, a.amount) for a in result.allocations] == [
        ("ana", Decimal("32000"))
    ]
    assert result.uncovered == 0


def test_no_payments_allocates_nothing_and_covers_nothing() -> None:
    result = allocate([ANA, LUIS], [])

    assert result.allocations == []
    assert result.uncovered == Decimal("86000")


def test_the_order_received_is_the_order_applied() -> None:
    """El orden es parte del contrato: dos cobros idénticos tienen que repartir igual."""
    forward = allocate([ANA, LUIS], [_p("40000")])
    backward = allocate([LUIS, ANA], [_p("40000")])

    assert forward.allocations[0].order_id == "ana"
    assert backward.allocations[0].order_id == "luis"
