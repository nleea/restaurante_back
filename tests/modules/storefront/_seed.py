"""Direct-DB seeding helpers for the public Storefront tests.

The storefront endpoints are unauthenticated, so tests hit them straight through the
``client`` (tenant resolved from the ``demo`` subdomain) and seed the catalog directly
via ``SessionFactory`` — no login, no RBAC. Mirrors the orders test seeding style.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select

from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.menu.infrastructure.models import (
    AddonModel,
    CategoryModel,
    ProductAddonModel,
    ProductModel,
    ProductPriceModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import DiningTableModel
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeItemModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.tenancy.models import BranchModel, TenantModel


@dataclass
class SeededMenu:
    branch_id: uuid.UUID
    category_id: uuid.UUID
    product_id: uuid.UUID
    variant_id: uuid.UUID
    addon_id: uuid.UUID
    removable_name: str
    staple_name: str


async def demo_tenant_id() -> uuid.UUID:
    async with SessionFactory() as session:
        tenant = (
            await session.execute(select(TenantModel).where(TenantModel.slug == "demo"))
        ).scalar_one()
        return tenant.id


async def seed_primary_branch(
    *, is_primary: bool = True, code: str = "b1", is_active: bool = True
) -> uuid.UUID:
    """A branch. ``code`` is slug-form because it addresses the branch in the public URL."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        branch = BranchModel(
            tenant_id=tenant_id,
            code=code,
            name=f"Branch {code}",
            is_primary=is_primary,
            is_active=is_active,
        )
        session.add(branch)
        await session.commit()
        await session.refresh(branch)
        return branch.id


async def seed_dining_table(
    branch_id: uuid.UUID,
    *,
    number: str = "5",
    code: str = "M5CODE",
    is_active: bool = True,
) -> uuid.UUID:
    """Una mesa con su código impreso ya fijado, para poder escanearla en el test.

    El código se pasa a mano en vez de dejar que lo acuñe el repositorio: aquí interesa
    direccionar una mesa CONOCIDA desde la URL, no ejercitar el generador (eso ya lo prueban
    los tests de la comanda).
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        table = DiningTableModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            number=number,
            code=code,
            capacity=4,
            is_active=is_active,
        )
        session.add(table)
        await session.commit()
        await session.refresh(table)
        return table.id


async def seed_branch_price(
    branch_id: uuid.UUID, product_id: uuid.UUID, price: str
) -> None:
    """Price an existing product at another branch (products are tenant-level)."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        session.add(
            ProductPriceModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                product_id=product_id,
                price=Decimal(price),
                is_active=True,
            )
        )
        await session.commit()


async def seed_menu(branch_id: uuid.UUID, *, price: str = "28000.00") -> SeededMenu:
    """One active category → product → sellable variant, with a branch price, an addon,
    and two recipe ingredients: a customer-removable one ("Cebolla") and a staple ("Sal").
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        category = CategoryModel(
            tenant_id=tenant_id, name="Ceviches", position=0, is_active=True
        )
        session.add(category)
        await session.flush()

        product = ProductModel(
            tenant_id=tenant_id,
            category_id=category.id,
            name="Ceviche Mixto",
            description="Fresco del día",
            image_url="https://img.local/ceviche.png",
            is_active=True,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product.id, name="Porción", is_active=True
        )
        session.add(variant)
        await session.flush()

        unit = UnitOfMeasureModel(name="unit", abbreviation="und")
        session.add(unit)
        await session.flush()

        session.add(
            ProductPriceModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                product_id=product.id,
                price=Decimal(price),
                is_active=True,
            )
        )

        addon = AddonModel(
            tenant_id=tenant_id, name="Extra Limón", price=Decimal("6000"), is_active=True
        )
        session.add(addon)
        await session.flush()
        session.add(
            ProductAddonModel(
                tenant_id=tenant_id, product_id=product.id, addon_id=addon.id
            )
        )

        removable = IngredientModel(
            tenant_id=tenant_id,
            name="Cebolla",
            unit_of_measure_id=unit.id,
            is_active=True,
            is_customer_removable=True,
        )
        staple = IngredientModel(
            tenant_id=tenant_id,
            name="Sal",
            unit_of_measure_id=unit.id,
            is_active=True,
            is_customer_removable=False,
        )
        session.add_all([removable, staple])
        await session.flush()
        for ingredient in (removable, staple):
            session.add(
                RecipeItemModel(
                    tenant_id=tenant_id,
                    product_variant_id=variant.id,
                    ingredient_id=ingredient.id,
                    quantity=Decimal("1"),
                    unit_of_measure_id=unit.id,
                )
            )

        await session.commit()
        return SeededMenu(
            branch_id=branch_id,
            category_id=category.id,
            product_id=product.id,
            variant_id=variant.id,
            addon_id=addon.id,
            removable_name="Cebolla",
            staple_name="Sal",
        )


async def seed_inactive_noise(branch_id: uuid.UUID) -> None:
    """An inactive category (with an otherwise-active product) and an inactive product
    under a fresh active category — neither may appear in the public menu."""
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        dead_category = CategoryModel(
            tenant_id=tenant_id, name="Archivados", position=9, is_active=False
        )
        live_category = CategoryModel(
            tenant_id=tenant_id, name="Bebidas", position=1, is_active=True
        )
        session.add_all([dead_category, live_category])
        await session.flush()

        session.add(
            ProductModel(
                tenant_id=tenant_id,
                category_id=dead_category.id,
                name="Producto en categoría muerta",
                is_active=True,
            )
        )
        session.add(
            ProductModel(
                tenant_id=tenant_id,
                category_id=live_category.id,
                name="Producto inactivo",
                is_active=False,
            )
        )
        await session.commit()


async def seed_extra_variant(
    seeded: SeededMenu, *, name: str, price: str
) -> uuid.UUID:
    """Otro producto vendible en la misma categoría y sucursal; devuelve su variante.

    Reutiliza la unidad y el ingrediente que ya sembró `seed_menu`: lo que hace falta aquí
    es una variante CON receta y CON precio —las dos redes de seguridad de la venta—, no un
    catálogo nuevo.
    """
    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        product = ProductModel(
            tenant_id=tenant_id,
            category_id=seeded.category_id,
            name=name,
            is_active=True,
        )
        session.add(product)
        await session.flush()

        variant = ProductVariantModel(
            tenant_id=tenant_id, product_id=product.id, name="Porción", is_active=True
        )
        session.add(variant)
        await session.flush()

        session.add(
            ProductPriceModel(
                tenant_id=tenant_id,
                branch_id=seeded.branch_id,
                product_id=product.id,
                price=Decimal(price),
                is_active=True,
            )
        )

        ingredient = (
            await session.execute(
                select(IngredientModel).where(
                    IngredientModel.tenant_id == tenant_id,
                    IngredientModel.name == seeded.staple_name,
                )
            )
        ).scalar_one()
        unit = (await session.execute(select(UnitOfMeasureModel).limit(1))).scalar_one()
        session.add(
            RecipeItemModel(
                tenant_id=tenant_id,
                product_variant_id=variant.id,
                ingredient_id=ingredient.id,
                quantity=Decimal("1"),
                unit_of_measure_id=unit.id,
            )
        )
        await session.commit()
        return variant.id


async def seed_delivery_ready(branch_id: uuid.UUID) -> None:
    """Deja la sede en condiciones de TOMAR domicilios: pin en el mapa y una banda de tarifa.

    Ambas cosas son lo que la carta pública exige antes de aceptar un domicilio, y por buena
    razón: sin ellas el pedido se acepta, nadie puede ponerle precio, y el cliente se queda
    esperando un enlace de pago que no existe. Un test de domicilios que no siembre esto está
    probando una sede que en producción diría "hoy no repartimos".
    """
    from decimal import Decimal

    from restaurante.modules.delivery.infrastructure.models import (
        DeliverySettingModel,
        DeliveryTariffBandModel,
    )

    tenant_id = await demo_tenant_id()
    async with SessionFactory() as session:
        session.add(
            DeliverySettingModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                latitude=Decimal("11.5444"),
                longitude=Decimal("-72.9072"),
            )
        )
        session.add(
            DeliveryTariffBandModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                max_distance_km=Decimal("6.000"),
                fee=Decimal("6000.00"),
                position=0,
            )
        )
        await session.commit()
