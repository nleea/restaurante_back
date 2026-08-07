"""La chit dice la cantidad de la variante que se pidió, no la del producto.

Las tareas viven en `product_stations`, que es por producto, y la receta es por variante. Antes
la tarea era una cadena opaca y la sencilla y la doble recibían la misma: `"Carne 150 g / 300 g"`,
con la mitad de la información equivocada en cada una de las dos comandas.

Lo que estos tests fijan: que la tarea recuerde su insumo, que el ruteo la resuelva contra la
receta de la variante pedida, y que ninguna de las dos cosas pueda impedir que el ticket se cree
— es el camino crítico de toda comanda.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.kitchen.infrastructure.models import ProductStationModel
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeItemModel,
)
from restaurante.shared.database import SessionFactory
from tests.modules.kitchen.test_kitchen_api import (
    _assign_role,
    _create_branch,
    _create_order_with_item,
    _create_station,
    _demo_ids,
    _login,
)


async def _units() -> tuple[uuid.UUID, uuid.UUID]:
    """`kg` con `g` como sub-unidad: la familia que hace que 0.150 se lea 150 g."""
    async with SessionFactory() as s:
        kilo = UnitOfMeasureModel(
            name=f"Kilo-{uuid.uuid4().hex[:6]}", abbreviation="kg"
        )
        s.add(kilo)
        await s.flush()
        gram = UnitOfMeasureModel(
            name=f"Gramo-{uuid.uuid4().hex[:6]}",
            abbreviation="g",
            base_unit_id=kilo.id,
            conversion_factor=Decimal("0.001"),
        )
        s.add(gram)
        await s.commit()
        await s.refresh(kilo)
        return kilo.id, gram.id


async def _dish_with_two_variants(
    unit_id: uuid.UUID,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Un plato con sencilla (0.150) y doble (0.300) del mismo insumo."""
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as s:
        category = CategoryModel(tenant_id=tenant_id, name=f"C-{uuid.uuid4().hex[:6]}")
        s.add(category)
        await s.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name="Hamburguesa"
        )
        s.add(product)
        await s.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id,
            name="Carne de res",
            unit_of_measure_id=unit_id,
            is_active=True,
        )
        s.add(ingredient)
        await s.flush()
        variants = []
        for name, quantity in (("Sencilla", "0.150"), ("Doble", "0.300")):
            variant = ProductVariantModel(
                tenant_id=tenant_id,
                product_id=product.id,
                name=name,
                is_active=True,
            )
            s.add(variant)
            await s.flush()
            s.add(
                RecipeItemModel(
                    tenant_id=tenant_id,
                    product_variant_id=variant.id,
                    ingredient_id=ingredient.id,
                    quantity=Decimal(quantity),
                    unit_of_measure_id=unit_id,
                )
            )
            variants.append(variant.id)
        await s.commit()
        return product.id, ingredient.id, variants[0], variants[1]


async def _map(product_id: uuid.UUID, station_id: uuid.UUID, tasks: list) -> None:
    """Escribe la asignación directo, para poder guardar también la forma vieja."""
    tenant_id, _ = await _demo_ids()
    async with SessionFactory() as s:
        s.add(
            ProductStationModel(
                tenant_id=tenant_id,
                product_id=product_id,
                kitchen_station_id=uuid.UUID(str(station_id)),
                tasks=tasks,
            )
        )
        await s.commit()


async def _route(
    client: AsyncClient, headers: dict[str, str], order_id: uuid.UUID
) -> list[dict]:
    resp = await client.post(f"/kitchen/orders/{order_id}/route", headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["tickets"]


async def test_each_variant_gets_its_own_amount(client: AsyncClient) -> None:
    """El caso que motivó todo: la doble dice 300 g y la sencilla 150 g."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    kilo, _gram = await _units()
    product_id, ingredient_id, small, double = await _dish_with_two_variants(kilo)
    await _map(
        product_id,
        station_id,
        [{"label": "Carne de res", "ingredient_id": str(ingredient_id)}],
    )

    small_order, _ = await _create_order_with_item(branch_id, small)
    double_order, _ = await _create_order_with_item(branch_id, double)

    small_tickets = await _route(client, headers, small_order)
    double_tickets = await _route(client, headers, double_order)

    # 0.150 kg se lee 150 g: nadie pesa 0.15 kg de carne.
    assert small_tickets[0]["tasks"] == ["Carne de res 150 g"]
    assert double_tickets[0]["tasks"] == ["Carne de res 300 g"]


async def test_a_hand_written_step_travels_verbatim(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    kilo, _gram = await _units()
    product_id, ingredient_id, small, _double = await _dish_with_two_variants(kilo)
    await _map(
        product_id,
        station_id,
        [
            {"label": "Carne de res", "ingredient_id": str(ingredient_id)},
            {"label": "Emplatar", "ingredient_id": None},
        ],
    )

    order_id, _ = await _create_order_with_item(branch_id, small)
    tickets = await _route(client, headers, order_id)

    assert tickets[0]["tasks"] == ["Carne de res 150 g", "Emplatar"]


async def test_an_ingredient_the_variant_does_not_use_is_not_emitted(
    client: AsyncClient,
) -> None:
    """Decirle al cocinero que ponga algo que ese plato no lleva es un error de comida."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    kilo, _gram = await _units()
    product_id, ingredient_id, small, _double = await _dish_with_two_variants(kilo)
    ghost = uuid.uuid4()
    await _map(
        product_id,
        station_id,
        [
            {"label": "Carne de res", "ingredient_id": str(ingredient_id)},
            {"label": "Tomate", "ingredient_id": str(ghost)},
        ],
    )

    order_id, _ = await _create_order_with_item(branch_id, small)
    tickets = await _route(client, headers, order_id)

    assert tickets[0]["tasks"] == ["Carne de res 150 g"]


async def test_a_mapping_saved_in_the_old_shape_still_routes(
    client: AsyncClient,
) -> None:
    """Sin backfill: una asignación anterior al cambio sigue enrutando, verbatim."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    kilo, _gram = await _units()
    product_id, _ingredient_id, small, _double = await _dish_with_two_variants(kilo)
    await _map(product_id, station_id, ["Carne", "Emplatar"])

    order_id, _ = await _create_order_with_item(branch_id, small)
    tickets = await _route(client, headers, order_id)

    assert tickets[0]["tasks"] == ["Carne", "Emplatar"]


async def test_a_dish_without_a_recipe_still_gets_its_ticket(
    client: AsyncClient,
) -> None:
    """Degradación, no fallo: enrutar es el camino crítico de toda comanda."""
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    kilo, _gram = await _units()
    product_id, _ingredient_id, small, _double = await _dish_with_two_variants(kilo)
    # La receta de la variante se borra DESPUÉS de mapear: nada resuelve, y aun así sale.
    async with SessionFactory() as s:
        for item in (
            await s.execute(
                select(RecipeItemModel).where(
                    RecipeItemModel.product_variant_id == small
                )
            )
        ).scalars():
            await s.delete(item)
        await s.commit()
    await _map(product_id, station_id, [{"label": "Solo un paso"}])

    order_id, _ = await _create_order_with_item(branch_id, small)
    tickets = await _route(client, headers, order_id)

    assert len(tickets) == 1
    assert tickets[0]["tasks"] == ["Solo un paso"]


async def test_routing_stays_idempotent(client: AsyncClient) -> None:
    await _assign_role("admin")
    headers = await _login(client)
    branch_id = await _create_branch()
    station_id = await _create_station(client, headers, branch_id)
    kilo, _gram = await _units()
    product_id, ingredient_id, small, _double = await _dish_with_two_variants(kilo)
    await _map(
        product_id,
        station_id,
        [{"label": "Carne de res", "ingredient_id": str(ingredient_id)}],
    )

    order_id, _ = await _create_order_with_item(branch_id, small)
    first = await _route(client, headers, order_id)
    second = await _route(client, headers, order_id)

    assert len(first) == 1
    assert second == []
