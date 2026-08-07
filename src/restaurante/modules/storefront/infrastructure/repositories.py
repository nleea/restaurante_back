"""Persistence adapter for the public Storefront module over SQLAlchemy async.

Two responsibilities, both deliberately narrow:

- A **customer-safe** menu read-model assembled server-side (categories + products with
  primary-branch price, one sellable variant, available addons and the recipe-derived
  removable ingredients). It never selects cost, BOM quantities or other internal fields.
- Composition-root helpers the public order flow needs: resolving the tenant's primary
  branch and lazily provisioning the "Pedidos web" system employee (person + user + role +
  employee) so the NOT-NULL ``orders.employee_id`` is satisfied without a logged-in user.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import exists, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.identity.infrastructure.models import (
    PersonModel,
    RoleModel,
    UserModel,
)
from restaurante.modules.menu.infrastructure.models import (
    AddonModel,
    CategoryModel,
    ProductAddonModel,
    ProductModel,
    ProductPriceModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import (
    DiningTableModel,
    OrderModel,
)
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeItemModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.modules.storefront.domain.entities import (
    StoreAddon,
    StoreBranch,
    StoreCategory,
    StoreMenu,
    StoreProduct,
    StoreTable,
    StoreVariant,
)
from restaurante.shared.tenancy.models import BranchModel

# El estado de una sesión de caja abierta. Se repite aquí en vez de importarlo de `cash` para
# no atar la carta pública al módulo de caja: lo único que se necesita es leer una fila.
_CASH_OPEN = "open"

# Sentinel login for the per-tenant web-orders employee. `users` is unique on
# (tenant_id, email), so the same address is safely reused across tenants.
_SYSTEM_EMAIL = "pedidos-web@storefront.local"
_SYSTEM_EMPLOYEE_NAME = "Pedidos web"
_SYSTEM_PASSWORD_PLACEHOLDER = "!"  # unusable hash — this account never logs in


class SqlAlchemyStorefrontRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def link_order_contact(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, contact_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_update(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.tenant_id == tenant_id)
            .values(whatsapp_contact_id=contact_id)
        )
        await self._session.commit()

    # --- Branch resolution -------------------------------------------------
    async def get_primary_branch_id(self, tenant_id: uuid.UUID) -> uuid.UUID | None:
        stmt = (
            select(BranchModel.id)
            .where(
                BranchModel.tenant_id == tenant_id,
                BranchModel.is_active.is_(True),
            )
            .order_by(BranchModel.is_primary.desc(), BranchModel.created_at)
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_branch_id_by_code(
        self, tenant_id: uuid.UUID, code: str
    ) -> uuid.UUID | None:
        stmt = select(BranchModel.id).where(
            BranchModel.tenant_id == tenant_id,
            BranchModel.code == code,
            BranchModel.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_active_table_by_code(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, code: str
    ) -> StoreTable | None:
        # `branch_id` va en el WHERE y no se comprueba después: el código sólo es único dentro
        # de su sede, así que buscarlo sin la sede podría encontrar la mesa 5 de otra sucursal.
        stmt = (
            select(
                DiningTableModel.id,
                DiningTableModel.number,
                DiningTableModel.branch_id,
                BranchModel.name.label("branch_name"),
            )
            .join(BranchModel, BranchModel.id == DiningTableModel.branch_id)
            .where(
                DiningTableModel.tenant_id == tenant_id,
                DiningTableModel.branch_id == branch_id,
                DiningTableModel.code == code,
                DiningTableModel.is_active.is_(True),
                BranchModel.is_active.is_(True),
            )
        )
        row = (await self._session.execute(stmt)).first()
        if row is None:
            return None
        return StoreTable(
            id=row.id,
            number=row.number,
            branch_id=row.branch_id,
            branch_name=row.branch_name,
        )

    async def has_open_cash_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool:
        stmt = select(
            exists().where(
                CashSessionModel.tenant_id == tenant_id,
                CashSessionModel.branch_id == branch_id,
                CashSessionModel.status == _CASH_OPEN,
            )
        )
        return bool((await self._session.execute(stmt)).scalar())

    async def list_active_branches(self, tenant_id: uuid.UUID) -> list[StoreBranch]:
        stmt = (
            select(
                BranchModel.id,
                BranchModel.code,
                BranchModel.name,
                BranchModel.address,
                BranchModel.phone,
            )
            .where(
                BranchModel.tenant_id == tenant_id,
                BranchModel.is_active.is_(True),
            )
            .order_by(BranchModel.is_primary.desc(), BranchModel.name.asc())
        )
        rows = (await self._session.execute(stmt)).all()
        return [
            StoreBranch(
                id=row.id,
                code=row.code,
                name=row.name,
                address=row.address,
                phone=row.phone,
            )
            for row in rows
        ]

    # --- System employee ---------------------------------------------------
    async def _existing_system_employee(
        self, tenant_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = (
            select(EmployeeModel.id)
            .join(UserModel, EmployeeModel.user_id == UserModel.id)
            .where(
                EmployeeModel.tenant_id == tenant_id,
                UserModel.email == _SYSTEM_EMAIL,
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def _any_role_id(self, tenant_id: uuid.UUID) -> uuid.UUID | None:
        stmt = (
            select(RoleModel.id)
            .where(
                RoleModel.is_active.is_(True),
                (RoleModel.tenant_id == tenant_id) | RoleModel.is_global.is_(True),
            )
            .order_by(RoleModel.is_global.desc())
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def resolve_system_employee(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID:
        existing = await self._existing_system_employee(tenant_id)
        if existing is not None:
            return existing

        person = PersonModel(first_name="Pedidos", last_name="Web")
        self._session.add(person)
        await self._session.flush()

        user = UserModel(
            tenant_id=tenant_id,
            email=_SYSTEM_EMAIL,
            hashed_password=_SYSTEM_PASSWORD_PLACEHOLDER,
            name=_SYSTEM_EMPLOYEE_NAME,
            person_id=person.id,
            is_active=True,
        )
        self._session.add(user)
        await self._session.flush()

        role_id = await self._any_role_id(tenant_id)
        if role_id is None:
            role = RoleModel(tenant_id=tenant_id, name="Sistema", is_active=True)
            self._session.add(role)
            await self._session.flush()
            role_id = role.id

        employee = EmployeeModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            user_id=user.id,
            role_id=role_id,
            is_active=True,
        )
        self._session.add(employee)
        await self._session.commit()
        await self._session.refresh(employee)
        return employee.id

    # --- Menu read-model ---------------------------------------------------
    async def build_menu(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> StoreMenu:
        cat_rows = (
            await self._session.execute(
                select(CategoryModel)
                .where(
                    CategoryModel.tenant_id == tenant_id,
                    CategoryModel.is_active.is_(True),
                )
                .order_by(CategoryModel.position, CategoryModel.name)
            )
        ).scalars().all()
        active_category_ids = {c.id for c in cat_rows}
        if not active_category_ids:
            return StoreMenu(categories=[], products=[])

        product_rows = (
            await self._session.execute(
                select(ProductModel)
                .where(
                    ProductModel.tenant_id == tenant_id,
                    ProductModel.is_active.is_(True),
                    ProductModel.category_id.in_(active_category_ids),
                )
                .order_by(ProductModel.name)
            )
        ).scalars().all()

        price_map: dict[uuid.UUID, Decimal] = {}
        for product_id, price in await self._session.execute(
            select(ProductPriceModel.product_id, ProductPriceModel.price).where(
                ProductPriceModel.tenant_id == tenant_id,
                ProductPriceModel.branch_id == branch_id,
                ProductPriceModel.is_active.is_(True),
            )
        ):
            price_map.setdefault(product_id, price)

        variant_map: dict[uuid.UUID, uuid.UUID] = {}
        for variant_id, product_id in await self._session.execute(
            select(ProductVariantModel.id, ProductVariantModel.product_id)
            .where(
                ProductVariantModel.tenant_id == tenant_id,
                ProductVariantModel.is_active.is_(True),
            )
            .order_by(ProductVariantModel.product_id, ProductVariantModel.name)
        ):
            variant_map.setdefault(product_id, variant_id)

        addon_map: dict[uuid.UUID, list[StoreAddon]] = {}
        for product_id, addon_id, name, price in await self._session.execute(
            select(
                ProductAddonModel.product_id,
                AddonModel.id,
                AddonModel.name,
                AddonModel.price,
            )
            .join(AddonModel, ProductAddonModel.addon_id == AddonModel.id)
            .where(
                ProductAddonModel.tenant_id == tenant_id,
                AddonModel.is_active.is_(True),
            )
            .order_by(AddonModel.name)
        ):
            addon_map.setdefault(product_id, []).append(
                StoreAddon(id=addon_id, name=name, price=price)
            )

        removable_map = await self._removable_ingredients(
            tenant_id, set(variant_map.values())
        )

        products = [
            StoreProduct(
                id=p.id,
                category_id=p.category_id,
                name=p.name,
                description=p.description,
                image_url=p.image_url,
                price=price_map.get(p.id),
                variant_id=variant_map.get(p.id),
                addons=addon_map.get(p.id, []),
                removable_ingredients=(
                    removable_map.get(variant_map[p.id], [])
                    if p.id in variant_map
                    else []
                ),
            )
            for p in product_rows
        ]
        categories = [StoreCategory(id=c.id, name=c.name) for c in cat_rows]
        return StoreMenu(categories=categories, products=products)

    async def _removable_ingredients(
        self, tenant_id: uuid.UUID, variant_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, list[str]]:
        if not variant_ids:
            return {}
        result: dict[uuid.UUID, list[str]] = {}
        for variant_id, name in await self._session.execute(
            select(RecipeItemModel.product_variant_id, IngredientModel.name)
            .join(IngredientModel, RecipeItemModel.ingredient_id == IngredientModel.id)
            .where(
                RecipeItemModel.tenant_id == tenant_id,
                RecipeItemModel.product_variant_id.in_(variant_ids),
                IngredientModel.is_customer_removable.is_(True),
                IngredientModel.is_active.is_(True),
            )
            .order_by(RecipeItemModel.id)
        ):
            names = result.setdefault(variant_id, [])
            if name not in names:  # dedupe, preserve order
                names.append(name)
        return result

    # --- Order-intake lookups ---------------------------------------------
    async def sellable_variant_product(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> uuid.UUID | None:
        product_id = (
            await self._session.execute(
                select(ProductVariantModel.product_id).where(
                    ProductVariantModel.tenant_id == tenant_id,
                    ProductVariantModel.id == variant_id,
                    ProductVariantModel.is_active.is_(True),
                )
            )
        ).scalar_one_or_none()
        if product_id is None:
            return None
        has_recipe = bool(
            (
                await self._session.execute(
                    select(
                        exists().where(
                            RecipeItemModel.tenant_id == tenant_id,
                            RecipeItemModel.product_variant_id == variant_id,
                        )
                    )
                )
            ).scalar_one()
        )
        return product_id if has_recipe else None

    async def product_price(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, branch_id: uuid.UUID
    ) -> Decimal | None:
        stmt = (
            select(ProductPriceModel.price)
            .where(
                ProductPriceModel.tenant_id == tenant_id,
                ProductPriceModel.product_id == product_id,
                ProductPriceModel.branch_id == branch_id,
                ProductPriceModel.is_active.is_(True),
            )
            .limit(1)
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def addon_price(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID
    ) -> Decimal | None:
        stmt = select(AddonModel.price).where(
            AddonModel.tenant_id == tenant_id,
            AddonModel.id == addon_id,
            AddonModel.is_active.is_(True),
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    # --- Describir lo que YA está en un pedido -----------------------------
    async def describe_variants(
        self, tenant_id: uuid.UUID, variant_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, StoreVariant]:
        wanted = set(variant_ids)
        if not wanted:
            return {}
        rows = (
            await self._session.execute(
                select(
                    ProductVariantModel.id,
                    ProductVariantModel.product_id,
                    ProductModel.name,
                )
                .join(ProductModel, ProductVariantModel.product_id == ProductModel.id)
                .where(
                    ProductVariantModel.tenant_id == tenant_id,
                    ProductVariantModel.id.in_(wanted),
                )
            )
        ).all()
        removable_map = await self._removable_ingredients(tenant_id, wanted)
        return {
            row.id: StoreVariant(
                id=row.id,
                product_id=row.product_id,
                product_name=row.name,
                removable_ingredients=removable_map.get(row.id, []),
            )
            for row in rows
        }

    async def addon_names(
        self, tenant_id: uuid.UUID, addon_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        wanted = set(addon_ids)
        if not wanted:
            return {}
        rows = (
            await self._session.execute(
                select(AddonModel.id, AddonModel.name).where(
                    AddonModel.tenant_id == tenant_id,
                    AddonModel.id.in_(wanted),
                )
            )
        ).all()
        return {row.id: row.name for row in rows}

    async def branch_phone(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> str | None:
        stmt = select(BranchModel.phone).where(
            BranchModel.tenant_id == tenant_id, BranchModel.id == branch_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()
