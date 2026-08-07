"""Derivar de la receta qué estaciones prepara un producto y qué le debe cada una.

La receta ya sabía de qué está hecho un plato y la asignación de estaciones ya sabía quién lo
cocina, pero nunca se hablaron: la lista de tareas del KDS se tecleaba a mano y se desincronizaba
en silencio. El insumo es el dato que ambos lados comparten.

El contrato que estos tests protegen por encima de todo: la sugerencia SÓLO propone. Ni una fila
de `product_stations` se mueve por pedirla, porque enrutar lee sólo lo guardado y una receta
editada no debe reescribir una comanda que ya salió.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from httpx import AsyncClient
from scripts.seed import seed_rbac
from sqlalchemy import select

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.identity.infrastructure.models import UserModel
from restaurante.modules.identity.infrastructure.repositories import (
    SqlAlchemyRbacRepository,
)
from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    ProductStationModel,
)
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
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from tests.conftest import TEST_EMAIL, TEST_PASSWORD


async def _tenant_id() -> uuid.UUID:
    async with SessionFactory() as s:
        return (
            await s.execute(select(TenantModel.id).where(TenantModel.slug == "demo"))
        ).scalar_one()


async def _login(client: AsyncClient, role: str = "admin") -> dict[str, str]:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        user_id = (
            await s.execute(select(UserModel.id).where(UserModel.email == TEST_EMAIL))
        ).scalar_one()
        roles = await seed_rbac(s)
        await s.commit()
        await SqlAlchemyRbacRepository(s).assign_user_role(
            tenant_id, user_id, roles[role].id
        )
        await s.commit()
    resp = await client.post(
        "/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _branch(code: str = "B1") -> uuid.UUID:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        branch = BranchModel(
            tenant_id=tenant_id,
            code=f"{code}-{uuid.uuid4().hex[:4]}",
            name=code,
            is_active=True,
        )
        s.add(branch)
        await s.commit()
        await s.refresh(branch)
        return branch.id


async def _station(branch_id: uuid.UUID, name: str) -> uuid.UUID:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        station = KitchenStationModel(
            tenant_id=tenant_id, branch_id=branch_id, name=name
        )
        s.add(station)
        await s.commit()
        await s.refresh(station)
        return station.id


async def _ingredient(name: str, station_id: uuid.UUID | None = None) -> uuid.UUID:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        unit = UnitOfMeasureModel(name=f"u-{uuid.uuid4().hex[:6]}", abbreviation="g")
        s.add(unit)
        await s.flush()
        ingredient = IngredientModel(
            tenant_id=tenant_id,
            name=name,
            unit_of_measure_id=unit.id,
            default_station_id=station_id,
        )
        s.add(ingredient)
        await s.commit()
        await s.refresh(ingredient)
        return ingredient.id


async def _product(name: str = "Hamburguesa") -> uuid.UUID:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        category = CategoryModel(tenant_id=tenant_id, name=f"Cat-{name[:6]}")
        s.add(category)
        await s.flush()
        product = ProductModel(
            tenant_id=tenant_id, category_id=category.id, name=name
        )
        s.add(product)
        await s.commit()
        await s.refresh(product)
        return product.id


async def _variant(product_id: uuid.UUID, name: str) -> uuid.UUID:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product_id, name=name, is_active=False
        )
        s.add(variant)
        await s.commit()
        await s.refresh(variant)
        return variant.id


async def _recipe_line(
    variant_id: uuid.UUID, ingredient_id: uuid.UUID, quantity: str = "1"
) -> None:
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        unit = (
            await s.execute(
                select(IngredientModel.unit_of_measure_id).where(
                    IngredientModel.id == ingredient_id
                )
            )
        ).scalar_one()
        s.add(
            RecipeItemModel(
                tenant_id=tenant_id,
                product_variant_id=variant_id,
                ingredient_id=ingredient_id,
                quantity=Decimal(quantity),
                unit_of_measure_id=unit,
            )
        )
        await s.commit()


async def _save_mapping(
    product_id: uuid.UUID, station_id: uuid.UUID, tasks: list[str]
) -> None:
    """Una asignación ya confirmada, como la dejaría una persona en configuración."""
    tenant_id = await _tenant_id()
    async with SessionFactory() as s:
        s.add(
            ProductStationModel(
                tenant_id=tenant_id,
                product_id=product_id,
                kitchen_station_id=station_id,
                tasks=tasks,
            )
        )
        await s.commit()


async def _count_mappings(product_id: uuid.UUID) -> int:
    async with SessionFactory() as s:
        rows = (
            await s.execute(
                select(ProductStationModel).where(
                    ProductStationModel.product_id == product_id
                )
            )
        ).scalars()
        return len(list(rows))


async def _suggest(
    client: AsyncClient,
    headers: dict[str, str],
    product_id: uuid.UUID,
    branch_id: uuid.UUID,
) -> dict:
    resp = await client.get(
        f"/kitchen/products/{product_id}/station-suggestion",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _labels(station: dict) -> list[str]:
    """Las etiquetas guardables: nombre a secas, SIN cantidad.

    La cantidad no vive en la etiqueta porque depende de la variante que se pida, y eso sólo se
    sabe al enrutar.
    """
    return [t["label"] for t in station["tasks"]]


def _amounts(station: dict) -> list[list[str]]:
    """Lo que el panel muestra: una cantidad por variante distinta."""
    return [t["amounts"] for t in station["tasks"]]


# --- Agrupación por estación -------------------------------------------------
async def test_groups_ingredients_by_their_station(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    cold = await _station(branch_id, "Fría")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))
    await _recipe_line(variant_id, await _ingredient("Lechuga", cold))

    body = await _suggest(client, headers, product_id, branch_id)

    by_name = {s["station_name"]: s for s in body["stations"]}
    assert _labels(by_name["Parrilla"]) == ["Carne"]
    assert _labels(by_name["Fría"]) == ["Lechuga"]
    assert body["unassigned_ingredients"] == []


async def test_union_across_variants_not_per_variant(client: AsyncClient) -> None:
    """Si la variante grande mete un insumo de otra estación, esa estación hace falta."""
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    fryer = await _station(branch_id, "Fritos")
    product_id = await _product()
    small = await _variant(product_id, "Pequeña")
    large = await _variant(product_id, "Grande")
    await _recipe_line(small, await _ingredient("Carne", grill))
    await _recipe_line(large, await _ingredient("Papas", fryer))

    body = await _suggest(client, headers, product_id, branch_id)

    assert {s["station_name"] for s in body["stations"]} == {"Parrilla", "Fritos"}


async def test_shared_ingredient_yields_one_task_and_both_variants(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    small = await _variant(product_id, "Pequeña")
    large = await _variant(product_id, "Grande")
    beef = await _ingredient("Carne", grill)
    await _recipe_line(small, beef)
    await _recipe_line(large, beef)

    body = await _suggest(client, headers, product_id, branch_id)

    station = body["stations"][0]
    assert _labels(station) == ["Carne"]
    assert sorted(station["from_variants"]) == ["Grande", "Pequeña"]


# --- La cantidad ------------------------------------------------------------
# "Carne de res" no le dice al cocinero lo que necesita saber; "Carne de res 300 g" sí. La
# cantidad ya estaba en la receta y era justo lo que la derivación tiraba a la basura.
async def test_the_task_carries_the_amount_from_the_recipe(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne de res", grill), "300")

    body = await _suggest(client, headers, product_id, branch_id)

    assert _labels(body["stations"][0]) == ["Carne de res"]
    assert _amounts(body["stations"][0]) == [["300 g"]]


async def test_scale_zeros_are_dropped(client: AsyncClient) -> None:
    """La columna guarda 300.000 por su escala, no porque el pase necesite tres decimales."""
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill), "300.000")

    body = await _suggest(client, headers, product_id, branch_id)

    assert _amounts(body["stations"][0]) == [["300 g"]]


async def test_a_real_decimal_survives(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Sal", grill), "1.500")

    body = await _suggest(client, headers, product_id, branch_id)

    assert _amounts(body["stations"][0]) == [["1.5 g"]]


async def test_variants_with_different_amounts_list_both(client: AsyncClient) -> None:
    """La receta es por variante y la estación por producto: sencilla y doble no coinciden.

    Se listan las dos en vez de elegir una. Inventar un solo número sería decirle al cocinero
    algo que la mitad de las veces está mal; verlas hace visible la decisión, y la persona
    ajusta el texto antes de guardar.
    """
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    small = await _variant(product_id, "Sencilla")
    double = await _variant(product_id, "Doble")
    beef = await _ingredient("Carne de res", grill)
    await _recipe_line(small, beef, "150")
    await _recipe_line(double, beef, "300")

    body = await _suggest(client, headers, product_id, branch_id)

    assert _labels(body["stations"][0]) == ["Carne de res"]
    assert _amounts(body["stations"][0]) == [["150 g", "300 g"]]


async def test_the_same_amount_across_variants_is_not_repeated(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    small = await _variant(product_id, "Sencilla")
    double = await _variant(product_id, "Doble")
    cheese = await _ingredient("Queso", grill)
    await _recipe_line(small, cheese, "20")
    await _recipe_line(double, cheese, "20")

    body = await _suggest(client, headers, product_id, branch_id)

    assert _amounts(body["stations"][0]) == [["20 g"]]


# --- Insumos sin estación ----------------------------------------------------
async def test_ingredients_without_a_station_are_reported_not_dropped(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))
    await _recipe_line(variant_id, await _ingredient("Sal", None))

    body = await _suggest(client, headers, product_id, branch_id)

    assert _labels(body["stations"][0]) == ["Carne"]
    unassigned = body["unassigned_ingredients"]
    assert [i["name"] for i in unassigned] == ["Sal"]
    assert unassigned[0]["default_station_in_other_branch"] is False
    # Y no se coló como tarea de ninguna estación.
    assert all("Sal" not in _labels(s) for s in body["stations"])


async def test_station_of_another_branch_is_flagged_not_proposed(
    client: AsyncClient,
) -> None:
    """El desajuste tenant/branch se absorbe aquí, no en el esquema."""
    headers = await _login(client)
    branch_id = await _branch("B1")
    other_branch = await _branch("B2")
    foreign = await _station(other_branch, "Parrilla ajena")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", foreign))

    body = await _suggest(client, headers, product_id, branch_id)

    assert body["stations"] == []
    assert body["unassigned_ingredients"][0]["name"] == "Carne"
    assert body["unassigned_ingredients"][0]["default_station_in_other_branch"] is True


# --- Bordes ------------------------------------------------------------------
async def test_product_without_recipe_returns_empty_200(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    product_id = await _product("Sin receta")
    await _variant(product_id, "Única")

    body = await _suggest(client, headers, product_id, branch_id)

    assert body["stations"] == []
    assert body["unassigned_ingredients"] == []


async def test_unknown_product_404(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _branch()

    resp = await client.get(
        f"/kitchen/products/{uuid.uuid4()}/station-suggestion",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"


async def test_product_of_another_tenant_404(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    async with SessionFactory() as s:
        other = TenantModel(slug=f"other-{uuid.uuid4().hex[:6]}", name="Other")
        s.add(other)
        await s.flush()
        category = CategoryModel(tenant_id=other.id, name="Ajena")
        s.add(category)
        await s.flush()
        product = ProductModel(
            tenant_id=other.id, category_id=category.id, name="Producto ajeno"
        )
        s.add(product)
        await s.commit()
        await s.refresh(product)
        foreign_product_id = product.id

    resp = await client.get(
        f"/kitchen/products/{foreign_product_id}/station-suggestion",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 404


async def test_requires_authentication(client: AsyncClient) -> None:
    branch_id = await _branch()
    product_id = await _product()

    resp = await client.get(
        f"/kitchen/products/{product_id}/station-suggestion",
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 401


async def test_requires_the_kitchen_read_permission(client: AsyncClient) -> None:
    """Un rol sin `kitchen.read` no puede mirar la configuración derivada."""
    headers = await _login(client, role="cashier")
    branch_id = await _branch()
    product_id = await _product()

    resp = await client.get(
        f"/kitchen/products/{product_id}/station-suggestion",
        headers=headers,
        params={"branch_id": str(branch_id)},
    )

    assert resp.status_code == 403


# --- El contrato central: sugerir no escribe ---------------------------------
async def test_asking_for_a_suggestion_writes_nothing(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))

    assert await _count_mappings(product_id) == 0
    await _suggest(client, headers, product_id, branch_id)
    await _suggest(client, headers, product_id, branch_id)

    # Ni una fila, ni siquiera pidiéndola dos veces.
    assert await _count_mappings(product_id) == 0


# --- Deriva ------------------------------------------------------------------
async def test_recipe_gained_an_ingredient_after_the_mapping_was_saved(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))
    await _save_mapping(product_id, grill, ["Carne"])

    # La receta gana un insumo DESPUÉS de que la asignación quedó guardada.
    await _recipe_line(variant_id, await _ingredient("Tocineta", grill))

    body = await _suggest(client, headers, product_id, branch_id)

    station = body["stations"][0]
    assert station["missing_from_saved"] == ["Tocineta"]
    assert station["saved_no_longer_implied"] == []
    # La copia guardada sigue intacta: se avisa, no se repara sola.
    async with SessionFactory() as s:
        saved = (
            await s.execute(
                select(ProductStationModel).where(
                    ProductStationModel.product_id == product_id
                )
            )
        ).scalar_one()
        assert saved.tasks == ["Carne"]


async def test_recipe_lost_an_ingredient_after_the_mapping_was_saved(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))
    await _save_mapping(product_id, grill, ["Carne", "Tocineta"])

    body = await _suggest(client, headers, product_id, branch_id)

    station = body["stations"][0]
    assert station["saved_no_longer_implied"] == ["Tocineta"]
    assert station["missing_from_saved"] == []


async def test_saved_tasks_that_are_not_ingredients_are_reported_never_removed(
    client: AsyncClient,
) -> None:
    """"Emplatar" no es un insumo y aun así nadie lo borra: por eso la copia se guarda."""
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))
    await _save_mapping(product_id, grill, ["Carne", "Emplatar"])

    body = await _suggest(client, headers, product_id, branch_id)

    assert body["stations"][0]["saved_no_longer_implied"] == ["Emplatar"]
    async with SessionFactory() as s:
        saved = (
            await s.execute(
                select(ProductStationModel).where(
                    ProductStationModel.product_id == product_id
                )
            )
        ).scalar_one()
        assert "Emplatar" in list(saved.tasks)


async def test_mapping_in_sync_reports_no_drift(client: AsyncClient) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))
    await _save_mapping(product_id, grill, ["Carne"])

    body = await _suggest(client, headers, product_id, branch_id)

    station = body["stations"][0]
    assert station["missing_from_saved"] == []
    assert station["saved_no_longer_implied"] == []


async def test_a_never_configured_station_is_new_not_drifted(
    client: AsyncClient,
) -> None:
    """Sin fila guardada no hay nada que reconciliar: es una propuesta, no una deriva."""
    headers = await _login(client)
    branch_id = await _branch()
    grill = await _station(branch_id, "Parrilla")
    product_id = await _product()
    variant_id = await _variant(product_id, "Sencilla")
    await _recipe_line(variant_id, await _ingredient("Carne", grill))

    body = await _suggest(client, headers, product_id, branch_id)

    station = body["stations"][0]
    assert _labels(station) == ["Carne"]
    assert station["missing_from_saved"] == []
    assert station["saved_no_longer_implied"] == []


# --- Override por línea de receta --------------------------------------------
# "¿Dónde va el arroz?" no tiene respuesta global: se cocina en un plato y se fríe en otro. La
# línea de receta es el par (plato, insumo) donde la pregunta sí tiene respuesta.
async def _set_line_station(
    variant_id: uuid.UUID, ingredient_id: uuid.UUID, station_id: uuid.UUID | None
) -> None:
    async with SessionFactory() as s:
        line = (
            await s.execute(
                select(RecipeItemModel).where(
                    RecipeItemModel.product_variant_id == variant_id,
                    RecipeItemModel.ingredient_id == ingredient_id,
                )
            )
        ).scalar_one()
        line.station_id = station_id
        await s.commit()


async def test_the_recipe_line_station_wins_over_the_ingredient_default(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    griddle = await _station(branch_id, "Plancha")
    fryer = await _station(branch_id, "Freidora")
    product_id = await _product("Arroz Frito")
    variant_id = await _variant(product_id, "Única")
    rice = await _ingredient("Arroz", griddle)  # por defecto se cocina
    await _recipe_line(variant_id, rice)
    await _set_line_station(variant_id, rice, fryer)  # en ESTE plato se fríe

    body = await _suggest(client, headers, product_id, branch_id)

    assert [s["station_name"] for s in body["stations"]] == ["Freidora"]


async def test_without_an_override_the_ingredient_default_is_used(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    griddle = await _station(branch_id, "Plancha")
    product_id = await _product("Arroz de Camarón")
    variant_id = await _variant(product_id, "Única")
    await _recipe_line(variant_id, await _ingredient("Arroz", griddle))

    body = await _suggest(client, headers, product_id, branch_id)

    assert [s["station_name"] for s in body["stations"]] == ["Plancha"]


async def test_an_override_on_one_dish_does_not_move_the_others(
    client: AsyncClient,
) -> None:
    """Es un override por plato: el default sigue cubriendo a todos los demás."""
    headers = await _login(client)
    branch_id = await _branch()
    griddle = await _station(branch_id, "Plancha")
    fryer = await _station(branch_id, "Freidora")
    rice = await _ingredient("Arroz", griddle)

    fried = await _product("Arroz Frito")
    fried_variant = await _variant(fried, "Única")
    await _recipe_line(fried_variant, rice)
    await _set_line_station(fried_variant, rice, fryer)

    boiled = await _product("Arroz Blanco")
    boiled_variant = await _variant(boiled, "Única")
    await _recipe_line(boiled_variant, rice)

    fried_body = await _suggest(client, headers, fried, branch_id)
    boiled_body = await _suggest(client, headers, boiled, branch_id)

    assert [s["station_name"] for s in fried_body["stations"]] == ["Freidora"]
    assert [s["station_name"] for s in boiled_body["stations"]] == ["Plancha"]


async def test_neither_line_nor_default_still_reports_unassigned(
    client: AsyncClient,
) -> None:
    headers = await _login(client)
    branch_id = await _branch()
    product_id = await _product("Sin estación")
    variant_id = await _variant(product_id, "Única")
    await _recipe_line(variant_id, await _ingredient("Arroz", None))

    body = await _suggest(client, headers, product_id, branch_id)

    assert body["stations"] == []
    assert [i["name"] for i in body["unassigned_ingredients"]] == ["Arroz"]
