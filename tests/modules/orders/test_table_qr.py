"""El QR de una mesa. Lo que se protege aquí es que lo IMPRESO no pueda estar mal.

Un enlace de WhatsApp equivocado se corrige mandando otro. Una calcomanía equivocada hay que
despegarla de diez mesas, y el error no se descubre hasta que un cliente la escanea sentado.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient

from restaurante.modules.orders.domain.table_qr import table_qr_svg
from restaurante.shared.links import table_order_url
from tests.modules.orders.test_orders_api import (
    _assign_role,
    _create_branch,
    _login,
)

_BASE = "https://wsquote.uk"


# --- La URL: función pura, un solo sitio donde se decide la forma -------------
def test_url_carries_branch_and_table_in_the_path() -> None:
    url = table_order_url(_BASE, "demo", "centro", "M5CODE")

    assert url == "https://demo.wsquote.uk/store/centro/table/M5CODE"


def test_url_prefixes_the_tenant_subdomain() -> None:
    """El subdominio no es cosmético: es lo único que dice de qué negocio es la carta."""
    assert table_order_url(_BASE, "otro", "centro", "M5CODE").startswith(
        "https://otro.wsquote.uk/"
    )


def test_url_is_empty_without_a_public_domain() -> None:
    """Media URL impresa en una calcomanía es el peor resultado: no falla hasta que la escanean."""
    assert table_order_url("", "demo", "centro", "M5CODE") == ""


def test_url_escapes_codes_that_would_break_the_path() -> None:
    """Hoy los códigos son alfanuméricos, pero quien los cambie mañana no tiene por qué saberlo."""
    url = table_order_url(_BASE, "demo", "sede/rara", "M5/CODE")

    assert "sede%2Frara" in url
    assert "M5%2FCODE" in url
    # La ruta sigue teniendo cuatro segmentos: una barra suelta dentro de un código no puede
    # partirla en silencio y mandar el pedido a otra parte.
    assert url.split("://", 1)[1].count("/") == 4


# --- El dibujo ----------------------------------------------------------------
def test_svg_encodes_the_url() -> None:
    svg = table_qr_svg("https://demo.wsquote.uk/store/centro/table/M5CODE")

    assert svg.lstrip().startswith("<svg")
    assert "</svg>" in svg


def test_svg_scales_instead_of_cropping() -> None:
    """El fallo que rompió los primeros QR impresos: salían recortados y no los leía nadie.

    Sin `viewBox`, el SVG tiene un tamaño intrínseco fijo y el CSS no puede cambiarlo: darle
    `max-width: 180px` encogía la CAJA y dejaba el dibujo a 392 px, así que sólo se veía su
    esquina superior izquierda. Un QR recortado es un QR muerto — y no falla en pantalla de
    forma evidente, falla cuando alguien apunta el teléfono.
    """
    svg = table_qr_svg("https://demo.wsquote.uk/store/centro/table/M5CODE")

    assert "viewBox=" in svg
    # Y NO puede llevar medidas fijas, que son las que ganaban sobre el CSS.
    assert "width=" not in svg
    assert "height=" not in svg


def test_svg_has_an_opaque_light_background() -> None:
    """La zona tranquila existe para dar contraste; transparente no da ninguno.

    Por defecto `segno` deja el claro transparente, así que el margen se quedaba del color de
    lo que hubiera debajo — papel de color, tarjeta con fondo — y el lector perdía el borde
    que necesita para encontrar el código.
    """
    svg = table_qr_svg("https://demo.wsquote.uk/store/centro/table/M5CODE")

    assert '#fff' in svg


def test_svg_refuses_an_empty_url() -> None:
    """Codificar "" daría un QR legible que lleva a ninguna parte — y se descubriría impreso."""
    try:
        table_qr_svg("")
    except ValueError:
        return
    raise AssertionError("una URL vacía tenía que reventar aquí, no en la calcomanía")


def test_svg_uses_high_error_correction() -> None:
    """Va pegado a una mesa: se mancha de grasa y se raya con los platos.

    El nivel alto se paga con un dibujo más denso —más módulos para la misma URL— a cambio de
    que siga leyéndose con casi un tercio del área destruida.
    """
    url = "https://demo.wsquote.uk/store/centro/table/M5CODE"
    import segno

    assert len(table_qr_svg(url)) > len(_svg_at(segno.make(url, error="l")))


def _svg_at(qr: object) -> str:
    import io

    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", scale=8, border=4, xmldecl=False)  # type: ignore[attr-defined]
    return buffer.getvalue().decode("utf-8")


# --- El endpoint --------------------------------------------------------------
async def _table(client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID) -> dict:
    resp = await client.post(
        "/orders/tables",
        headers=headers,
        json={"branch_id": str(branch_id), "number": "5", "capacity": 4},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_endpoint_returns_the_svg_and_the_url_it_encodes(
    client: AsyncClient, monkeypatch
) -> None:
    """La URL viaja al lado del dibujo: un QR es opaco y nadie revisaría lo que no puede leer."""
    from restaurante.shared.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "storefront_base_url", _BASE, raising=False)

    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code="centro")
    table = await _table(client, headers, branch_id)

    resp = await client.get(f"/orders/tables/{table['id']}/qr", headers=headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["url"] == (
        f"https://demo.wsquote.uk/store/centro/table/{table['code']}"
    )
    assert body["svg"].lstrip().startswith("<svg")


async def test_endpoint_refuses_when_no_public_domain_is_configured(
    client: AsyncClient, monkeypatch
) -> None:
    from restaurante.shared.config import get_settings

    monkeypatch.setattr(get_settings(), "storefront_base_url", "", raising=False)

    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch(code="centro")
    table = await _table(client, headers, branch_id)

    resp = await client.get(f"/orders/tables/{table['id']}/qr", headers=headers)

    assert resp.status_code == 422
    assert "STOREFRONT_BASE_URL" in resp.json()["detail"]


async def test_endpoint_404s_on_an_unknown_table(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)

    resp = await client.get(f"/orders/tables/{uuid.uuid4()}/qr", headers=headers)

    assert resp.status_code == 404


async def test_endpoint_is_permission_gated(client: AsyncClient) -> None:
    resp = await client.get(f"/orders/tables/{uuid.uuid4()}/qr")

    assert resp.status_code in (401, 403)
