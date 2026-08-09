"""El único sitio donde se calcula el precio de una línea.

Esta suite es el corazón del change y vigila cuatro propiedades que se rompen en silencio:

1. **La fórmula suma el recargo de la variante.** Es la del salón; el storefront no lo sumaba, y de
   ahí venía que los dos canales pudieran cobrar distinto por el mismo plato.
2. **El precio sale de la sede del PEDIDO.** Buscarlo por la sede "activa" de quien pide es el bug
   obvio: un cajero mirando otra sucursal cobraría con los precios de la suya.
3. **Sin precio en esa sede devuelve `None`, no cero.** Un `?? 0` en el camino del dinero es un
   regalo que nadie autorizó y que no se ve hasta que se cuenta el turno.
4. **Un precio en OTRA sede no vale.** Es el mismo punto 2 mirado desde el otro lado, y merece su
   propia prueba porque un `WHERE` al que se le olvida `branch_id` pasa las otras tres.

Se prueba contra el repositorio y **sin levantar la app**: toma `setup_db` en vez de `client` porque
lo que está en juego es una consulta, no un endpoint.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductPriceModel,
    ProductVariantModel,
    ProductVariantOptionModel,
    VariantGroupModel,
    VariantOptionModel,
)
from restaurante.modules.orders.infrastructure.repositories import (
    SqlAlchemyOrdersRepository,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel

BASE = Decimal("25000.00")
SURCHARGE = Decimal("5000.00")


async def _tenant_id() -> uuid.UUID:
    async with SessionFactory() as session:
        return (
            await session.execute(select(TenantModel).where(TenantModel.slug == "demo"))
        ).scalar_one().id


async def _branch(tenant_id: uuid.UUID, code: str) -> uuid.UUID:
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id, code=code, name=f"Sede {code}", is_active=True
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return branch.id


async def _variant(
    tenant_id: uuid.UUID, *, surcharge: Decimal | None = None
) -> tuple[uuid.UUID, uuid.UUID]:
    """Un producto con una variante. Con `surcharge`, la variante compone una opción con recargo.

    El recargo se monta como el sistema lo monta de verdad —grupo → opción → composición— y no
    escribiendo un número en la variante, porque **`extra_price` no es una columna de
    `product_variants`**: es la suma de las opciones que compone. Una prueba que lo simplificara
    dejaría de probar la consulta real.
    """
    async with SessionFactory() as session:
        category = CategoryModel(tenant_id=tenant_id, name=f"Cat {uuid.uuid4().hex[:6]}")
        session.add(category)
        await session.flush()
        product = ProductModel(
            tenant_id=tenant_id,
            category_id=category.id,
            name=f"Bandeja {uuid.uuid4().hex[:6]}",
            is_active=True,
        )
        session.add(product)
        await session.flush()
        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product.id, name="Grande", is_active=True
        )
        session.add(variant)
        await session.flush()

        if surcharge is not None:
            group = VariantGroupModel(
                tenant_id=tenant_id, product_id=product.id, name="Tamaño"
            )
            session.add(group)
            await session.flush()
            option = VariantOptionModel(
                tenant_id=tenant_id,
                variant_group_id=group.id,
                name="Grande",
                extra_price=surcharge,
            )
            session.add(option)
            await session.flush()
            session.add(
                ProductVariantOptionModel(
                    tenant_id=tenant_id,
                    product_variant_id=variant.id,
                    variant_option_id=option.id,
                )
            )
        await session.commit()
        return product.id, variant.id


async def _price(
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    branch_id: uuid.UUID,
    amount: Decimal,
    *,
    active: bool = True,
) -> None:
    async with SessionFactory() as session:
        session.add(
            ProductPriceModel(
                tenant_id=tenant_id,
                product_id=product_id,
                branch_id=branch_id,
                price=amount,
                is_active=active,
            )
        )
        await session.commit()


async def _resolve(
    tenant_id: uuid.UUID, variant_id: uuid.UUID, branch_id: uuid.UUID
) -> Decimal | None:
    async with SessionFactory() as session:
        return await SqlAlchemyOrdersRepository(session).resolve_line_price(
            tenant_id, variant_id, branch_id
        )


# --- La fórmula -------------------------------------------------------------
async def test_the_price_is_the_branch_price_plus_the_variant_surcharge(setup_db: None) -> None:
    """25000 + 5000 = 30000. La del salón, no la del storefront."""
    tenant_id = await _tenant_id()
    branch_id = await _branch(tenant_id, f"s-{uuid.uuid4().hex[:6]}")
    product_id, variant_id = await _variant(tenant_id, surcharge=SURCHARGE)
    await _price(tenant_id, product_id, branch_id, BASE)

    assert await _resolve(tenant_id, variant_id, branch_id) == Decimal("30000.00")


async def test_a_plain_variant_costs_the_branch_price(setup_db: None) -> None:
    """Sin opciones compuestas el recargo es cero, no `None`: hoy TODAS las variantes son así."""
    tenant_id = await _tenant_id()
    branch_id = await _branch(tenant_id, f"s-{uuid.uuid4().hex[:6]}")
    product_id, variant_id = await _variant(tenant_id)
    await _price(tenant_id, product_id, branch_id, BASE)

    assert await _resolve(tenant_id, variant_id, branch_id) == BASE


async def test_two_composed_options_both_add_up(setup_db: None) -> None:
    """El recargo es una SUMA, no una lectura. Con una sola opción esto pasaría igual."""
    tenant_id = await _tenant_id()
    branch_id = await _branch(tenant_id, f"s-{uuid.uuid4().hex[:6]}")
    product_id, variant_id = await _variant(tenant_id, surcharge=SURCHARGE)

    async with SessionFactory() as session:
        group = (
            await session.execute(
                select(VariantGroupModel).where(
                    VariantGroupModel.product_id == product_id
                )
            )
        ).scalar_one()
        option = VariantOptionModel(
            tenant_id=tenant_id,
            variant_group_id=group.id,
            name="Extra queso",
            extra_price=Decimal("2000.00"),
        )
        session.add(option)
        await session.flush()
        session.add(
            ProductVariantOptionModel(
                tenant_id=tenant_id,
                product_variant_id=variant_id,
                variant_option_id=option.id,
            )
        )
        await session.commit()

    await _price(tenant_id, product_id, branch_id, BASE)

    assert await _resolve(tenant_id, variant_id, branch_id) == Decimal("32000.00")


# --- La sede es la del pedido ----------------------------------------------
async def test_the_price_comes_from_the_given_branch(setup_db: None) -> None:
    """Mismo producto con dos precios; se cobra el de la sede que se pasa."""
    tenant_id = await _tenant_id()
    first = await _branch(tenant_id, f"a-{uuid.uuid4().hex[:6]}")
    second = await _branch(tenant_id, f"b-{uuid.uuid4().hex[:6]}")
    product_id, variant_id = await _variant(tenant_id)
    await _price(tenant_id, product_id, first, Decimal("10000.00"))
    await _price(tenant_id, product_id, second, Decimal("18000.00"))

    assert await _resolve(tenant_id, variant_id, first) == Decimal("10000.00")
    assert await _resolve(tenant_id, variant_id, second) == Decimal("18000.00")


# --- Sin precio: None, nunca cero -----------------------------------------
async def test_no_price_in_that_branch_is_none(setup_db: None) -> None:
    """`None` y no `Decimal(0)`. De esta distinción depende que la venta se rechace."""
    tenant_id = await _tenant_id()
    branch_id = await _branch(tenant_id, f"s-{uuid.uuid4().hex[:6]}")
    _, variant_id = await _variant(tenant_id)

    result = await _resolve(tenant_id, variant_id, branch_id)
    assert result is None
    assert result != Decimal(0)


async def test_a_price_in_another_branch_does_not_count(setup_db: None) -> None:
    """La que caza un `WHERE` al que se le olvidó `branch_id`: las otras pasarían igual."""
    tenant_id = await _tenant_id()
    priced = await _branch(tenant_id, f"a-{uuid.uuid4().hex[:6]}")
    other = await _branch(tenant_id, f"b-{uuid.uuid4().hex[:6]}")
    product_id, variant_id = await _variant(tenant_id)
    await _price(tenant_id, product_id, priced, BASE)

    assert await _resolve(tenant_id, variant_id, other) is None


async def test_an_inactive_price_does_not_count(setup_db: None) -> None:
    """Un precio apagado es un precio que el negocio retiró: no se vende a ese número ni a cero."""
    tenant_id = await _tenant_id()
    branch_id = await _branch(tenant_id, f"s-{uuid.uuid4().hex[:6]}")
    product_id, variant_id = await _variant(tenant_id)
    await _price(tenant_id, product_id, branch_id, BASE, active=False)

    assert await _resolve(tenant_id, variant_id, branch_id) is None


async def test_a_variant_of_another_tenant_is_none(setup_db: None) -> None:
    """El aislamiento, en el camino del dinero. Un precio de otro negocio no se cobra aquí."""
    tenant_id = await _tenant_id()
    branch_id = await _branch(tenant_id, f"s-{uuid.uuid4().hex[:6]}")
    product_id, variant_id = await _variant(tenant_id)
    await _price(tenant_id, product_id, branch_id, BASE)

    assert await _resolve(uuid.uuid4(), variant_id, branch_id) is None


async def test_an_unknown_variant_is_none(setup_db: None) -> None:
    tenant_id = await _tenant_id()
    branch_id = await _branch(tenant_id, f"s-{uuid.uuid4().hex[:6]}")

    assert await _resolve(tenant_id, uuid.uuid4(), branch_id) is None
