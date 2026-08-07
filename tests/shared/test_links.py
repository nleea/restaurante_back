"""Los enlaces públicos: un token mal puesto en un path es un cliente que no puede pagar."""

from restaurante.shared.links import (
    delivery_payment_url,
    order_edit_url,
    tenant_base_url,
)


def test_tenant_base_url_prefixes_the_slug() -> None:
    assert tenant_base_url("https://wsquote.uk", "demo") == "https://demo.wsquote.uk"


def test_delivery_payment_url_carries_tenant_and_token() -> None:
    assert (
        delivery_payment_url("https://wsquote.uk", "demo", "abc123")
        == "https://demo.wsquote.uk/payment/delivery/abc123"
    )


def test_delivery_payment_url_escapes_a_token_with_a_slash() -> None:
    """Un `/` sin escapar partiría la ruta y el enlace resolvería a otra pantalla."""
    assert (
        delivery_payment_url("https://menu.example", None, "abc/xyz")
        == "https://menu.example/payment/delivery/abc%2Fxyz"
    )


def test_delivery_payment_url_is_empty_without_a_configured_domain() -> None:
    """Media URL por WhatsApp es peor que ninguna: quien llama decide qué decir."""
    assert delivery_payment_url("", "demo", "abc123") == ""


def test_order_edit_url_keeps_its_shape() -> None:
    assert (
        order_edit_url("https://wsquote.uk", "demo", "tok")
        == "https://demo.wsquote.uk/my-order/tok"
    )
