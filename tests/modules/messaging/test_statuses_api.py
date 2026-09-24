"""El API de estados: componer, programar, y la previa de la audiencia.

Dos propiedades del contrato que no son obvias y que se prueban aquí:

- **un estado de texto sin color o sin fuente es un 422 al GUARDAR**, no un 400 del proveedor a las
  once de la mañana dentro de un worker,
- **la previa de audiencia itemiza las cuatro bajas**, porque un total no dice *por qué* bajó y una
  cifra sola se lee como cobertura completa.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio
from httpx import AsyncClient

from .conftest import (
    TEST_EMAIL,
    create_branch,
    create_employee,
    create_session_row,
    grant_only,
    login,
    post_inbound,
)


@pytest_asyncio.fixture
async def screen(client: AsyncClient) -> dict[str, Any]:
    """Una sede con número, un contacto que escribió, y sesión abierta con permisos de admin."""
    branch_id = await create_branch("centro", primary=True)
    await create_session_row(branch_id, "inst-centro")
    # `create_employee` es lo que le asigna el rol admin al usuario de la demo. Sin esto no tiene
    # ningún rol y todo da 403 — el mismo cableado que usa el fixture `inbox`.
    await create_employee(branch_id, TEST_EMAIL)
    headers = await login(client)
    await post_inbound(client, "inst-centro", message_id="a1", phone="+573001112233")
    return {"branch_id": str(branch_id), "headers": headers}


def _card(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "text",
        "content": "Hoy hay sancocho",
        "bg_color": "#0B3D2E",
        "font": 2,
        "slots": [{"weekday": 0, "minute": 660}],
    }
    payload.update(overrides)
    return payload


async def _post(client: AsyncClient, s: dict[str, Any], body: dict[str, Any]) -> Any:
    return await client.post(
        "/messaging/statuses",
        params={"branch_id": s["branch_id"]},
        headers=s["headers"],
        json=body,
    )


# --- Composición ------------------------------------------------------------
@pytest.mark.asyncio
async def test_a_text_card_is_created_with_its_schedule(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    response = await _post(client, screen, _card())

    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "text"
    assert body["bg_color"] == "#0B3D2E"
    assert body["font"] == 2
    assert body["slots"] == [{"minute": 660, "weekday": 0, "on_date": None}]


@pytest.mark.asyncio
async def test_a_text_card_without_a_background_colour_is_refused(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    """422 al guardar. El proveedor daría 400 al publicar, sin nadie mirando."""
    response = await _post(client, screen, _card(bg_color=None))

    assert response.status_code == 422
    assert "color" in response.text.lower()


@pytest.mark.asyncio
async def test_a_text_card_without_a_font_is_refused(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    response = await _post(client, screen, _card(font=None))

    assert response.status_code == 422
    assert "fuente" in response.text.lower()


@pytest.mark.asyncio
async def test_a_text_card_with_font_zero_is_refused(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    """El 0 es "sin fuente" para Evolution (`if (!status.font)`): 400 al publicar."""
    response = await _post(client, screen, _card(font=0))

    assert response.status_code == 422
    assert "fuente" in response.text.lower()


@pytest.mark.asyncio
async def test_a_text_card_with_a_font_outside_the_catalogue_is_refused(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    """El 3 no existe en `FontType`: no fallaría, se vería en otra letra."""
    response = await _post(client, screen, _card(font=3))

    assert response.status_code == 422
    assert "fuente" in response.text.lower()


@pytest.mark.asyncio
async def test_an_image_status_needs_neither(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    response = await _post(
        client,
        screen,
        _card(
            type="image",
            content="Menú del día",
            media_url="https://cdn.test/menu.jpg",
            caption="Menú del día",
            bg_color=None,
            font=None,
        ),
    )

    assert response.status_code == 201
    assert response.json()["caption"] == "Menú del día"


@pytest.mark.asyncio
async def test_an_image_status_without_the_uploaded_image_is_refused(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    response = await _post(
        client,
        screen,
        _card(type="image", content="Menú del día", bg_color=None, font=None),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_an_unknown_type_is_refused(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    assert (await _post(client, screen, _card(type="video"))).status_code == 422


# --- El horario -------------------------------------------------------------
@pytest.mark.asyncio
async def test_every_day_is_seven_slots(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    """Marcar los siete días ES "todos los días". No hay selector de recurrencia."""
    response = await _post(
        client,
        screen,
        _card(slots=[{"weekday": d, "minute": 660} for d in range(7)]),
    )

    assert response.status_code == 201
    assert len(response.json()["slots"]) == 7


@pytest.mark.asyncio
async def test_a_dated_slot_is_accepted(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    response = await _post(
        client, screen, _card(slots=[{"on_date": "2026-08-15", "minute": 1080}])
    )

    assert response.status_code == 201
    assert response.json()["slots"][0]["on_date"] == "2026-08-15"


@pytest.mark.asyncio
async def test_a_slot_with_a_weekday_and_a_date_is_refused(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    response = await _post(
        client,
        screen,
        _card(slots=[{"weekday": 0, "on_date": "2026-08-15", "minute": 660}]),
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_a_status_with_no_slots_is_allowed_but_never_publishes(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    """Guardar un borrador sin horario es legítimo; lo que no puede es salir solo."""
    response = await _post(client, screen, _card(slots=[]))

    assert response.status_code == 201
    assert response.json()["slots"] == []


# --- Ciclo de vida ----------------------------------------------------------
@pytest.mark.asyncio
async def test_saving_replaces_the_whole_schedule(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    created = (await _post(client, screen, _card())).json()

    updated = await client.put(
        f"/messaging/statuses/{created['id']}",
        params={"branch_id": screen["branch_id"]},
        headers=screen["headers"],
        json=_card(slots=[{"weekday": 4, "minute": 1110}]),
    )

    assert updated.status_code == 200
    assert updated.json()["slots"] == [
        {"minute": 1110, "weekday": 4, "on_date": None}
    ]


@pytest.mark.asyncio
async def test_a_status_can_be_deleted(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    created = (await _post(client, screen, _card())).json()
    params = {"branch_id": screen["branch_id"]}

    deleted = await client.delete(
        f"/messaging/statuses/{created['id']}", params=params, headers=screen["headers"]
    )
    assert deleted.status_code == 204

    gone = await client.get(
        f"/messaging/statuses/{created['id']}", params=params, headers=screen["headers"]
    )
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_statuses_are_listed_for_the_branch(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    await _post(client, screen, _card())
    await _post(client, screen, _card(content="Promo de la tarde"))

    listed = await client.get(
        "/messaging/statuses",
        params={"branch_id": screen["branch_id"]},
        headers=screen["headers"],
    )

    assert listed.status_code == 200
    assert len(listed.json()) == 2


# --- La previa de audiencia -------------------------------------------------
@pytest.mark.asyncio
async def test_the_audience_preview_itemises_its_reductions(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    """Los cuatro campos de exclusión existen SIEMPRE, aunque estén a cero.

    Que estén en el contrato es lo que impide que la pantalla enseñe sólo el total — y un total
    sobre una audiencia truncada se lee como cobertura completa.
    """
    response = await client.get(
        "/messaging/statuses/audience",
        params={"branch_id": screen["branch_id"]},
        headers=screen["headers"],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["addressed"] == 1
    assert body["total_candidates"] == 1
    for key in (
        "excluded_no_number",
        "excluded_opted_out",
        "excluded_inactive",
        "excluded_by_cap",
    ):
        assert body[key] == 0, key
    # El número que mide el riesgo: cuántas llamadas costaría.
    assert body["provider_calls"] == 1


@pytest.mark.asyncio
async def test_the_preview_never_talks_about_views(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    """El contrato no puede ofrecer un campo que sería mentira."""
    body = (
        await client.get(
            "/messaging/statuses/audience",
            params={"branch_id": screen["branch_id"]},
            headers=screen["headers"],
        )
    ).json()

    for forbidden in ("views", "viewed", "seen", "delivered"):
        assert forbidden not in body


@pytest.mark.asyncio
async def test_an_opted_out_contact_shows_up_in_the_preview_as_excluded(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    conversations = (
        await client.get(
            "/messaging/conversations",
            params={"branch_id": screen["branch_id"]},
            headers=screen["headers"],
        )
    ).json()
    await client.put(
        f"/messaging/conversations/{conversations[0]['id']}/status-opt-out",
        params={"branch_id": screen["branch_id"]},
        headers=screen["headers"],
        json={"opted_out": True},
    )

    body = (
        await client.get(
            "/messaging/statuses/audience",
            params={"branch_id": screen["branch_id"]},
            headers=screen["headers"],
        )
    ).json()

    assert body["addressed"] == 0
    assert body["excluded_opted_out"] == 1


# --- Historial y permisos ---------------------------------------------------
@pytest.mark.asyncio
async def test_a_fresh_status_has_no_publications(
    client: AsyncClient, screen: dict[str, Any]
) -> None:
    created = (await _post(client, screen, _card())).json()

    response = await client.get(
        f"/messaging/statuses/{created['id']}/publications",
        params={"branch_id": screen["branch_id"]},
        headers=screen["headers"],
    )

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_statuses_require_manage(client: AsyncClient) -> None:
    """`messaging.manage`, que ya está en el catálogo — sin permiso nuevo no hay que resembrar.

    `grant_only` va ANTES de cualquier petición autenticada: los permisos efectivos se cachean con
    TTL, así que una petición previa con el rol de admin los deja cacheados y el 403 nunca llega.
    """
    branch_id = await create_branch("centro", primary=True)
    await grant_only(["messaging.read", "messaging.attend"])
    headers = await login(client)
    params = {"branch_id": str(branch_id)}

    assert (
        await client.get("/messaging/statuses", params=params, headers=headers)
    ).status_code == 403
    assert (
        await client.get(
            "/messaging/statuses/audience", params=params, headers=headers
        )
    ).status_code == 403
    assert (
        await client.post(
            "/messaging/statuses", params=params, headers=headers, json=_card()
        )
    ).status_code == 403
