"""Lo que el pedido por QR cambia del lado de la comanda.

Tres cosas, y la tercera es la que muerde: el código impreso de la mesa, el comensal y el origen
de la comanda, y que la mesa deje de liberarse en cuanto UNA de sus comandas se cierra.
"""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.orders.application.use_cases.manage_orders import OrderService
from restaurante.modules.orders.domain.table_code import (
    ALPHABET,
    LENGTH,
    TableCodeExhaustedError,
    mint_table_code,
)
from restaurante.modules.orders.infrastructure.models import DiningTableModel
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.domain.errors import ValidationError
from tests.modules._cash import seed_open_cash_session
from tests.modules.orders.test_orders_api import (
    _assign_role,
    _create_branch,
    _create_employee,
    _create_variant,
    _demo_ids,
    _login,
)


async def _table(client: AsyncClient, headers: dict[str, str], branch_id: uuid.UUID, number: str):
    resp = await client.post(
        "/orders/tables",
        headers=headers,
        json={"branch_id": str(branch_id), "number": number, "capacity": 4},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _open_order(
    client: AsyncClient,
    headers: dict[str, str],
    branch_id: uuid.UUID,
    employee_id: uuid.UUID,
    table_id: str,
) -> str:
    resp = await client.post(
        "/orders",
        headers=headers,
        json={
            "branch_id": str(branch_id),
            "channel": "dine_in",
            "employee_id": str(employee_id),
            "dining_table_id": table_id,
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _table_status(table_id: str) -> str:
    async with SessionFactory() as session:
        model = (
            await session.execute(
                select(DiningTableModel).where(DiningTableModel.id == uuid.UUID(table_id))
            )
        ).scalar_one()
        return model.status


# --- El código de la calcomanía ---------------------------------------------
def test_mint_avoids_taken_codes() -> None:
    """El reintento es cortesía: da un código bueno a la primera cuando puede."""
    taken = {"AAAAAA"}
    codes = iter("AAAAAA" "BBBBBB")
    assert mint_table_code(taken, rng=lambda _: next(codes)) == "BBBBBB"


def test_mint_gives_up_loudly_instead_of_spinning() -> None:
    """Agotar ~887 millones de códigos significa generador roto, no mala suerte."""
    try:
        mint_table_code({"AAAAAA"}, rng=lambda _: "A")
    except TableCodeExhaustedError:
        return
    raise AssertionError("debía rendirse ruidosamente")


def test_alphabet_has_no_ambiguous_characters() -> None:
    """Quien no pueda escanear va a teclear lo que lee."""
    for ambiguous in "01OIL":
        assert ambiguous not in ALPHABET


async def test_table_is_minted_with_a_code(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    table = await _table(client, headers, branch_id, "1")

    assert table["code"] is not None
    assert len(table["code"]) == LENGTH
    assert set(table["code"]) <= set(ALPHABET)


async def test_codes_are_unique_within_a_branch(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()

    codes = {
        (await _table(client, headers, branch_id, str(n)))["code"] for n in range(1, 11)
    }

    assert len(codes) == 10


async def test_code_survives_renumbering(client: AsyncClient) -> None:
    """El número es del negocio y lo cambian; el código es del papel pegado a la mesa."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    table = await _table(client, headers, branch_id, "5")

    renumbered = await client.patch(
        f"/orders/tables/{table['id']}", headers=headers, json={"number": "12"}
    )

    assert renumbered.status_code == 200, renumbered.text
    assert renumbered.json()["number"] == "12"
    assert renumbered.json()["code"] == table["code"]


async def test_code_cannot_be_overwritten_through_update(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    table = await _table(client, headers, branch_id, "5")

    # Aunque alguien lo mande explícitamente: el código es inmutable en el repositorio, no por
    # una regla del endpoint.
    resp = await client.patch(
        f"/orders/tables/{table['id']}",
        headers=headers,
        json={"number": "5", "code": "ZZZZZZ"},
    )

    assert resp.status_code in (200, 422)
    async with SessionFactory() as session:
        stored = (
            await session.execute(
                select(DiningTableModel.code).where(
                    DiningTableModel.id == uuid.UUID(table["id"])
                )
            )
        ).scalar_one()
    assert stored == table["code"]


# --- El comensal y el origen ------------------------------------------------
async def test_order_defaults_to_staff_with_no_diner(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await seed_open_cash_session(branch_id, employee_id)
    table = await _table(client, headers, branch_id, "1")

    order_id = await _open_order(client, headers, branch_id, employee_id, table["id"])

    resp = await client.get(f"/orders/{order_id}", headers=headers)
    assert resp.json()["origin"] == "staff"
    assert resp.json()["diner_name"] is None


async def test_open_order_rejects_an_unknown_origin(client: AsyncClient) -> None:
    """El origen se valida en el CASO DE USO, que es por donde entra el camino público.

    La API autenticada no expone `origin` —una comanda que abre el personal es `staff` y punto—,
    así que un origen inventado sólo puede llegar desde dentro. Ahí es donde tiene que rebotar.
    """
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await seed_open_cash_session(branch_id, employee_id)
    tenant_id, _ = await _demo_ids()

    async with SessionFactory() as session:
        service = OrderService(repo=SqlAlchemyOrdersRepository(session))
        try:
            await service.open_order(
                tenant_id,
                branch_id,
                "dine_in",
                employee_id,
                origin="poltergeist",
            )
        except ValidationError as exc:
            assert "Origen inválido" in str(exc)
        else:
            raise AssertionError("un origen desconocido tenía que ser rechazado")

    assert headers  # la sesión autenticada sólo existe para sembrar el escenario


# --- La mesa se libera sólo cuando no queda nadie ---------------------------
async def test_table_stays_occupied_while_a_sibling_order_is_open(
    client: AsyncClient,
) -> None:
    """El primero que paga NO puede apagar la mesa para los que siguen comiendo."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await seed_open_cash_session(branch_id, employee_id)
    await _create_variant()
    table = await _table(client, headers, branch_id, "5")

    first = await _open_order(client, headers, branch_id, employee_id, table["id"])
    await _open_order(client, headers, branch_id, employee_id, table["id"])
    assert await _table_status(table["id"]) == "occupied"

    # Una comanda vacía (total 0) se cierra sin pagos: sirve para aislar el efecto sobre la mesa.
    closed = await client.post(f"/orders/{first}/close", headers=headers)
    assert closed.status_code == 200, closed.text

    assert await _table_status(table["id"]) == "occupied"


async def test_last_open_order_frees_the_table(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await seed_open_cash_session(branch_id, employee_id)
    table = await _table(client, headers, branch_id, "5")

    first = await _open_order(client, headers, branch_id, employee_id, table["id"])
    second = await _open_order(client, headers, branch_id, employee_id, table["id"])

    assert (await client.post(f"/orders/{first}/close", headers=headers)).status_code == 200
    assert await _table_status(table["id"]) == "occupied"
    assert (await client.post(f"/orders/{second}/close", headers=headers)).status_code == 200

    assert await _table_status(table["id"]) == "free"


async def test_cancelling_follows_the_same_rule(client: AsyncClient) -> None:
    """Cancelar es el gemelo de cerrar y comparte la corrección."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await seed_open_cash_session(branch_id, employee_id)
    table = await _table(client, headers, branch_id, "5")

    first = await _open_order(client, headers, branch_id, employee_id, table["id"])
    second = await _open_order(client, headers, branch_id, employee_id, table["id"])

    body = {"reason": "se fue", "requested_by_employee_id": str(employee_id)}
    assert (
        await client.post(f"/orders/{first}/cancel", headers=headers, json=body)
    ).status_code == 200
    assert await _table_status(table["id"]) == "occupied"

    assert (
        await client.post(f"/orders/{second}/cancel", headers=headers, json=body)
    ).status_code == 200
    assert await _table_status(table["id"]) == "free"


async def test_occupying_an_already_occupied_table_is_idempotent(
    client: AsyncClient,
) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    employee_id = await _create_employee(branch_id)
    await seed_open_cash_session(branch_id, employee_id)
    table = await _table(client, headers, branch_id, "7")

    await _open_order(client, headers, branch_id, employee_id, table["id"])
    assert await _table_status(table["id"]) == "occupied"
    await _open_order(client, headers, branch_id, employee_id, table["id"])

    assert await _table_status(table["id"]) == "occupied"
