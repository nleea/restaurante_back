"""Rich demo dataset seed for live testing / pilot rehearsal.

Layers a full operational dataset on top of the minimal baseline created by
``scripts.seed`` (demo tenant ``demo``, branch ``MAIN``, admin user and RBAC).
It fills the cross-module flow end to end so screens and reports are non-empty:

    units / geo -> staff & drivers -> supplies (insumos) -> inventory stock
    -> suppliers / purchasing -> menu & product variants -> recipes (BOM)
    -> customers -> delivery routes (rutas) / drivers / runs
    -> dining tables -> cash session -> orders / items / payments
    -> order deliveries -> finance expenses

Idempotent: rows are looked up by a natural key before insert, and the
transactional sample data (orders, runs, cash session) is guarded so a second
run does not duplicate anything. All rows are scoped to the ``demo`` tenant and
its branch; ids are set explicitly because the seed runs outside an HTTP request
(the automatic tenant filter has no context).

Usage:
    poetry run python -m scripts.seed_demo

Reset (drop everything, then reload):
    poetry run alembic downgrade base && poetry run alembic upgrade head
    poetry run python -m scripts.seed_demo

Login (from the baseline seed):
    subdomain: demo   email: admin@demo.com   password: admin1234
"""

from __future__ import annotations

import asyncio
from collections import Counter
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# Register every model in Base.metadata (cross-module FKs) before touching them.
import restaurante.shared.models_registry  # noqa: F401
from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.catalog.infrastructure.models import (
    CityModel,
    CountryModel,
    UnitOfMeasureModel,
)
from restaurante.modules.customers.infrastructure.models import CustomerModel
from restaurante.modules.delivery.infrastructure.models import (
    DeliveryRouteDriverModel,
    DeliveryRouteModel,
    DeliveryRunModel,
    OrderDeliveryModel,
)
from restaurante.modules.finance.infrastructure.models import (
    ExpenseCategoryModel,
    ExpenseModel,
)
from restaurante.modules.identity.domain.permissions_catalog import ADMIN_ROLE_NAME
from restaurante.modules.identity.infrastructure.models import (
    PersonModel,
    RoleModel,
    UserModel,
)
from restaurante.modules.inventory.infrastructure.models import (
    InventoryMovementModel,
    InventoryStockModel,
)
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductPriceModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import (
    DiningTableModel,
    OrderItemModel,
    OrderModel,
    OrderPaymentModel,
)
from restaurante.modules.purchasing.infrastructure.models import (
    PurchaseRequestItemModel,
    PurchaseRequestModel,
    SupplierIngredientModel,
    SupplierModel,
)
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeItemModel,
)
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.database import SessionFactory
from restaurante.shared.security.password import Argon2PasswordHasher
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from scripts.seed import DEMO_BRANCH_CODE, DEMO_SLUG
from scripts.seed import seed as seed_baseline

# --- status / value constants (plain strings: no DB enum) ---------------------
STATUS_RUN_PREPARING = "preparing"
DELIVERY_PENDING = "pending"
DELIVERY_ASSIGNED = "assigned"
DELIVERY_IN_TRANSIT = "in_transit"
DELIVERY_DELIVERED = "delivered"
CHANNEL_DINE_IN = "dine_in"
CHANNEL_DELIVERY = "delivery"
CHANNEL_TAKEOUT = "takeout"
PAY_CASH = "cash"
PAY_NEQUI = "nequi"
DEMO_USER_PASSWORD = "demo1234"

counts: Counter[str] = Counter()

M = TypeVar("M")


async def get_or_create(
    session: AsyncSession,
    model: type[M],
    *,
    defaults: dict[str, Any] | None = None,
    **filters: Any,
) -> tuple[M, bool]:
    """Look up ``model`` by ``filters``; create with ``filters + defaults`` if absent."""
    obj = (
        await session.execute(select(model).filter_by(**filters))
    ).scalar_one_or_none()
    if obj is not None:
        return obj, False
    obj = model(**filters, **(defaults or {}))
    session.add(obj)
    await session.flush()
    counts[model.__name__] += 1
    return obj, True


# --- reference data -----------------------------------------------------------
async def seed_units(session: AsyncSession) -> dict[str, UnitOfMeasureModel]:
    base = {}
    for name, abbr in [("Kilogramo", "kg"), ("Litro", "L"), ("Unidad", "und")]:
        unit, _ = await get_or_create(
            session, UnitOfMeasureModel, name=name, abbreviation=abbr
        )
        base[abbr] = unit
    for name, abbr, parent, factor in [
        ("Gramo", "g", "kg", Decimal("0.001")),
        ("Mililitro", "ml", "L", Decimal("0.001")),
    ]:
        unit, _ = await get_or_create(
            session,
            UnitOfMeasureModel,
            name=name,
            abbreviation=abbr,
            defaults={
                "base_unit_id": base[parent].id,
                "conversion_factor": factor,
            },
        )
        base[abbr] = unit
    return base


async def seed_geo(session: AsyncSession) -> CityModel:
    country, _ = await get_or_create(
        session, CountryModel, iso_code="CO", defaults={"name": "Colombia"}
    )
    city, _ = await get_or_create(
        session,
        CityModel,
        name="Bogotá",
        country_id=country.id,
        defaults={"state_province": "Cundinamarca"},
    )
    return city


# --- staff & drivers ----------------------------------------------------------
async def seed_staff(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    staff_role_id: Any,
    city_id: Any,
) -> dict[str, EmployeeModel]:
    hasher = Argon2PasswordHasher()
    specs = [
        ("Carlos", "Cajero", "carlos@demo.com", "CC1001", "cashier"),
        ("Diego", "Repartidor", "diego@demo.com", "CC1002", "driver1"),
        ("Daniela", "Moto", "daniela@demo.com", "CC1003", "driver2"),
        ("Camilo", "Cocina", "camilo@demo.com", "CC1004", "cook"),
    ]
    employees: dict[str, EmployeeModel] = {}
    for first, last, email, doc, key in specs:
        person, _ = await get_or_create(
            session,
            PersonModel,
            document_number=doc,
            defaults={
                "document_type": "CC",
                "first_name": first,
                "last_name": last,
                "city_id": city_id,
            },
        )
        user, _ = await get_or_create(
            session,
            UserModel,
            tenant_id=tenant_id,
            email=email,
            defaults={
                "person_id": person.id,
                "hashed_password": hasher.hash(DEMO_USER_PASSWORD),
                "name": f"{first} {last}",
                "is_active": True,
            },
        )
        employee, _ = await get_or_create(
            session,
            EmployeeModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            person_id=person.id,
            defaults={"user_id": user.id, "role_id": staff_role_id},
        )
        employees[key] = employee
    return employees


# --- supplies (insumos) & inventory ------------------------------------------
INGREDIENTS = [
    ("Carne de res", "kg", Decimal("25.000"), Decimal("5.000")),
    ("Pan de hamburguesa", "und", Decimal("200.000"), Decimal("40.000")),
    ("Queso cheddar", "kg", Decimal("8.000"), Decimal("2.000")),
    ("Tomate", "kg", Decimal("12.000"), Decimal("3.000")),
    ("Lechuga", "kg", Decimal("6.000"), Decimal("1.500")),
    ("Papa", "kg", Decimal("40.000"), Decimal("10.000")),
    ("Aceite vegetal", "L", Decimal("18.000"), Decimal("4.000")),
    ("Pollo", "kg", Decimal("15.000"), Decimal("4.000")),
    ("Sal", "kg", Decimal("10.000"), Decimal("2.000")),
    ("Gaseosa lata", "und", Decimal("120.000"), Decimal("24.000")),
]


async def seed_supplies(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    units: dict[str, UnitOfMeasureModel],
) -> dict[str, IngredientModel]:
    ingredients: dict[str, IngredientModel] = {}
    for name, unit_abbr, current, minimum in INGREDIENTS:
        ingredient, _ = await get_or_create(
            session,
            IngredientModel,
            tenant_id=tenant_id,
            name=name,
            defaults={"unit_of_measure_id": units[unit_abbr].id, "is_active": True},
        )
        ingredients[name] = ingredient
        await get_or_create(
            session,
            InventoryStockModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            ingredient_id=ingredient.id,
            defaults={"current_quantity": current, "min_stock": minimum},
        )
    return ingredients


async def seed_inventory_movements(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    ingredients: dict[str, IngredientModel],
    cook: EmployeeModel,
) -> None:
    existing = (
        await session.execute(
            select(func.count())
            .select_from(InventoryMovementModel)
            .where(InventoryMovementModel.branch_id == branch_id)
        )
    ).scalar_one()
    if existing:
        return
    for name, qty in [("Carne de res", Decimal("10.000")), ("Papa", Decimal("20.000"))]:
        session.add(
            InventoryMovementModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                ingredient_id=ingredients[name].id,
                type="in",
                reason="purchase",
                quantity=qty,
                employee_id=cook.id,
                notes="Reposición inicial de demo",
            )
        )
        counts["inventory_movements"] += 1


# --- purchasing ---------------------------------------------------------------
async def seed_suppliers(
    session: AsyncSession,
    tenant_id: Any,
    ingredients: dict[str, IngredientModel],
    units: dict[str, UnitOfMeasureModel],
) -> None:
    catalog = {
        "Distribuidora La 80": [
            ("Carne de res", "kg", Decimal("22000.00")),
            ("Pollo", "kg", Decimal("12000.00")),
            ("Queso cheddar", "kg", Decimal("18000.00")),
        ],
        "Panadería El Trigal": [
            ("Pan de hamburguesa", "und", Decimal("700.00")),
        ],
    }
    for supplier_name, items in catalog.items():
        supplier, _ = await get_or_create(
            session,
            SupplierModel,
            tenant_id=tenant_id,
            name=supplier_name,
            defaults={"is_active": True},
        )
        for ing_name, unit_abbr, price in items:
            await get_or_create(
                session,
                SupplierIngredientModel,
                tenant_id=tenant_id,
                supplier_id=supplier.id,
                ingredient_id=ingredients[ing_name].id,
                defaults={
                    "reference_price": price,
                    "unit_of_measure_id": units[unit_abbr].id,
                    "is_active": True,
                },
            )


async def seed_purchase_request(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    ingredients: dict[str, IngredientModel],
    units: dict[str, UnitOfMeasureModel],
    requester: EmployeeModel,
) -> None:
    existing = (
        await session.execute(
            select(func.count())
            .select_from(PurchaseRequestModel)
            .where(PurchaseRequestModel.branch_id == branch_id)
        )
    ).scalar_one()
    if existing:
        return
    request = PurchaseRequestModel(
        tenant_id=tenant_id,
        branch_id=branch_id,
        requested_by_employee_id=requester.id,
        status="pending",
        reason="Reposición semanal de insumos",
    )
    session.add(request)
    await session.flush()
    counts["purchase_requests"] += 1
    for ing_name, qty, unit_abbr in [
        ("Carne de res", Decimal("10.000"), "kg"),
        ("Pan de hamburguesa", Decimal("100.000"), "und"),
        ("Queso cheddar", Decimal("4.000"), "kg"),
    ]:
        session.add(
            PurchaseRequestItemModel(
                tenant_id=tenant_id,
                purchase_request_id=request.id,
                ingredient_id=ingredients[ing_name].id,
                requested_quantity=qty,
                unit_of_measure_id=units[unit_abbr].id,
            )
        )
        counts["purchase_request_items"] += 1


# --- menu & recipes -----------------------------------------------------------
MENU = [
    ("Hamburguesas", "Hamburguesa Clásica", Decimal("18000.00")),
    ("Hamburguesas", "Hamburguesa Doble", Decimal("26000.00")),
    ("Bebidas", "Gaseosa Lata", Decimal("5000.00")),
    ("Acompañamientos", "Papas Fritas", Decimal("8000.00")),
]
# product name -> [(ingredient name, qty, unit abbr)]
RECIPES = {
    "Hamburguesa Clásica": [
        ("Carne de res", Decimal("0.150"), "kg"),
        ("Pan de hamburguesa", Decimal("1.000"), "und"),
        ("Queso cheddar", Decimal("0.030"), "kg"),
        ("Tomate", Decimal("0.020"), "kg"),
        ("Lechuga", Decimal("0.015"), "kg"),
    ],
    "Hamburguesa Doble": [
        ("Carne de res", Decimal("0.300"), "kg"),
        ("Pan de hamburguesa", Decimal("1.000"), "und"),
        ("Queso cheddar", Decimal("0.060"), "kg"),
    ],
    "Papas Fritas": [
        ("Papa", Decimal("0.250"), "kg"),
        ("Aceite vegetal", Decimal("0.050"), "L"),
        ("Sal", Decimal("0.005"), "kg"),
    ],
    "Gaseosa Lata": [
        ("Gaseosa lata", Decimal("1.000"), "und"),
    ],
}


async def seed_menu(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
) -> dict[str, dict[str, Any]]:
    """Returns product name -> {variant, price}."""
    products: dict[str, dict[str, Any]] = {}
    for cat_name, prod_name, price in MENU:
        category, _ = await get_or_create(
            session, CategoryModel, tenant_id=tenant_id, name=cat_name
        )
        product, _ = await get_or_create(
            session,
            ProductModel,
            tenant_id=tenant_id,
            name=prod_name,
            defaults={"category_id": category.id, "is_active": True},
        )
        await get_or_create(
            session,
            ProductPriceModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            product_id=product.id,
            defaults={"price": price, "is_active": True},
        )
        variant, _ = await get_or_create(
            session,
            ProductVariantModel,
            tenant_id=tenant_id,
            product_id=product.id,
            name="Estándar",
            defaults={"is_active": True},
        )
        products[prod_name] = {"variant": variant, "price": price}
    return products


async def seed_recipes(
    session: AsyncSession,
    tenant_id: Any,
    products: dict[str, dict[str, Any]],
    ingredients: dict[str, IngredientModel],
    units: dict[str, UnitOfMeasureModel],
) -> None:
    for prod_name, items in RECIPES.items():
        variant = products[prod_name]["variant"]
        for ing_name, qty, unit_abbr in items:
            await get_or_create(
                session,
                RecipeItemModel,
                tenant_id=tenant_id,
                product_variant_id=variant.id,
                ingredient_id=ingredients[ing_name].id,
                defaults={
                    "quantity": qty,
                    "unit_of_measure_id": units[unit_abbr].id,
                },
            )


# --- customers ----------------------------------------------------------------
async def seed_customers(
    session: AsyncSession,
    tenant_id: Any,
    city_id: Any,
) -> list[CustomerModel]:
    specs = [
        ("María", "González", "CC2001", "3001112233"),
        ("Juan", "Pérez", "CC2002", "3002223344"),
        ("Ana", "Ramírez", "CC2003", "3003334455"),
    ]
    customers: list[CustomerModel] = []
    for first, last, doc, phone in specs:
        person, _ = await get_or_create(
            session,
            PersonModel,
            document_number=doc,
            defaults={
                "document_type": "CC",
                "first_name": first,
                "last_name": last,
                "phone": phone,
                "city_id": city_id,
            },
        )
        customer, _ = await get_or_create(
            session,
            CustomerModel,
            tenant_id=tenant_id,
            person_id=person.id,
            defaults={"is_active": True},
        )
        customers.append(customer)
    return customers


# --- delivery routes (rutas) --------------------------------------------------
async def seed_delivery_routes(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    employees: dict[str, EmployeeModel],
) -> dict[str, dict[str, Any]]:
    """Returns route name -> {route, run, driver}."""
    config = [
        ("Ruta Norte", "Chapinero, Usaquén, Cedritos", "driver1"),
        ("Ruta Sur", "Kennedy, Bosa, Tunjuelito", "driver2"),
    ]
    routes: dict[str, dict[str, Any]] = {}
    for name, zones, driver_key in config:
        route, _ = await get_or_create(
            session,
            DeliveryRouteModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            name=name,
            defaults={"covered_zones": zones, "is_active": True},
        )
        driver = employees[driver_key]
        await get_or_create(
            session,
            DeliveryRouteDriverModel,
            tenant_id=tenant_id,
            delivery_route_id=route.id,
            employee_id=driver.id,
            defaults={"is_active": True},
        )
        run, _ = await get_or_create(
            session,
            DeliveryRunModel,
            tenant_id=tenant_id,
            delivery_route_id=route.id,
            employee_id=driver.id,
            status=STATUS_RUN_PREPARING,
        )
        routes[name] = {"route": route, "run": run, "driver": driver}
    return routes


# --- dining tables ------------------------------------------------------------
async def seed_dining_tables(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
) -> list[DiningTableModel]:
    tables: list[DiningTableModel] = []
    for number in ["1", "2", "3", "4"]:
        table, _ = await get_or_create(
            session,
            DiningTableModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            number=number,
            defaults={"capacity": 4, "status": "free", "is_active": True},
        )
        tables.append(table)
    return tables


# --- cash session -------------------------------------------------------------
async def seed_cash_session(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    cashier: EmployeeModel,
) -> CashSessionModel:
    existing = (
        await session.execute(
            select(CashSessionModel).where(
                CashSessionModel.branch_id == branch_id,
                CashSessionModel.status == "open",
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing
    cash_session = CashSessionModel(
        tenant_id=tenant_id,
        branch_id=branch_id,
        opened_by_employee_id=cashier.id,
        opening_amount=Decimal("200000.00"),
        status="open",
    )
    session.add(cash_session)
    await session.flush()
    counts["cash_sessions"] += 1
    session.add(
        CashMovementModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            cash_session_id=cash_session.id,
            type="in",
            concept="Apertura de caja",
            amount=Decimal("200000.00"),
            method=PAY_CASH,
        )
    )
    counts["cash_movements"] += 1
    return cash_session


# --- orders / payments / deliveries ------------------------------------------
async def seed_orders(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    products: dict[str, dict[str, Any]],
    tables: list[DiningTableModel],
    customers: list[CustomerModel],
    routes: dict[str, dict[str, Any]],
    cash_session: CashSessionModel,
    cashier: EmployeeModel,
) -> None:
    existing = (
        await session.execute(
            select(func.count())
            .select_from(OrderModel)
            .where(OrderModel.branch_id == branch_id)
        )
    ).scalar_one()
    if existing:
        return

    route_list = list(routes.values())
    # (channel, [(product, qty)], table?, customer_idx?, pay, delivery_status?, route_idx?)
    plan: list[dict[str, Any]] = [
        {
            "channel": CHANNEL_DINE_IN,
            "items": [("Hamburguesa Clásica", 2), ("Gaseosa Lata", 2)],
            "table": tables[0],
            "pay": PAY_CASH,
        },
        {
            "channel": CHANNEL_DINE_IN,
            "items": [("Hamburguesa Doble", 1), ("Papas Fritas", 1)],
            "table": tables[1],
            "pay": PAY_CASH,
        },
        {
            "channel": CHANNEL_TAKEOUT,
            "items": [("Papas Fritas", 2)],
            "pay": PAY_NEQUI,
        },
        {
            "channel": CHANNEL_DELIVERY,
            "items": [("Hamburguesa Clásica", 1), ("Papas Fritas", 1)],
            "customer": 0,
            "pay": PAY_CASH,
            "delivery_status": DELIVERY_DELIVERED,
            "route": 0,
            "address": "Cra 13 # 85-32, Chapinero",
            "neighborhood": "Chapinero",
        },
        {
            "channel": CHANNEL_DELIVERY,
            "items": [("Hamburguesa Doble", 2)],
            "customer": 1,
            "pay": PAY_NEQUI,
            "delivery_status": DELIVERY_IN_TRANSIT,
            "route": 0,
            "address": "Calc 140 # 9-50, Cedritos",
            "neighborhood": "Cedritos",
        },
        {
            "channel": CHANNEL_DELIVERY,
            "items": [("Hamburguesa Clásica", 3), ("Gaseosa Lata", 3)],
            "customer": 2,
            "pay": PAY_CASH,
            "delivery_status": DELIVERY_PENDING,
            "route": 1,
            "address": "Cll 38 Sur # 78-12, Kennedy",
            "neighborhood": "Kennedy",
        },
    ]

    position: Counter[int] = Counter()
    for entry in plan:
        order = OrderModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            channel=entry["channel"],
            dining_table_id=entry["table"].id if entry.get("table") else None,
            customer_id=(
                customers[entry["customer"]].id if "customer" in entry else None
            ),
            employee_id=cashier.id,
            status="open",
            subtotal=Decimal("0.00"),
            discount=Decimal("0.00"),
            total=Decimal("0.00"),
        )
        session.add(order)
        await session.flush()
        counts["orders"] += 1

        subtotal = Decimal("0.00")
        for prod_name, qty in entry["items"]:
            price = products[prod_name]["price"]
            line_subtotal = price * qty
            subtotal += line_subtotal
            session.add(
                OrderItemModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    order_id=order.id,
                    product_variant_id=products[prod_name]["variant"].id,
                    quantity=qty,
                    unit_price=price,
                    line_subtotal=line_subtotal,
                    status="pending",
                )
            )
            counts["order_items"] += 1

        order.subtotal = subtotal
        order.total = subtotal
        session.add(
            OrderPaymentModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                order_id=order.id,
                cash_session_id=cash_session.id,
                amount=subtotal,
                method=entry["pay"],
                employee_id=cashier.id,
            )
        )
        counts["order_payments"] += 1

        if entry["channel"] == CHANNEL_DELIVERY:
            route_info = route_list[entry["route"]]
            status = entry["delivery_status"]
            assigned = status != DELIVERY_PENDING
            position[entry["route"]] += 1
            session.add(
                OrderDeliveryModel(
                    tenant_id=tenant_id,
                    order_id=order.id,
                    delivery_route_id=route_info["route"].id,
                    delivery_run_id=route_info["run"].id if assigned else None,
                    address_text=entry["address"],
                    neighborhood=entry["neighborhood"],
                    delivery_status=status,
                    route_position=position[entry["route"]],
                )
            )
            counts["order_deliveries"] += 1


# --- finance ------------------------------------------------------------------
async def seed_finance(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    cashier: EmployeeModel,
) -> None:
    category, _ = await get_or_create(
        session,
        ExpenseCategoryModel,
        tenant_id=tenant_id,
        name="Servicios",
        defaults={"is_active": True},
    )
    existing = (
        await session.execute(
            select(func.count())
            .select_from(ExpenseModel)
            .where(ExpenseModel.branch_id == branch_id)
        )
    ).scalar_one()
    if existing:
        return
    for description, amount in [
        ("Energía eléctrica", Decimal("450000.00")),
        ("Gas natural", Decimal("180000.00")),
    ]:
        session.add(
            ExpenseModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                expense_category_id=category.id,
                description=description,
                amount=amount,
                employee_id=cashier.id,
            )
        )
        counts["expenses"] += 1


# --- orchestrator -------------------------------------------------------------
async def seed_demo() -> None:
    # 1. Guarantee the baseline (tenant/branch/admin/RBAC) exists and is committed.
    await seed_baseline()

    async with SessionFactory() as session:
        tenant = (
            await session.execute(
                select(TenantModel).where(TenantModel.slug == DEMO_SLUG)
            )
        ).scalar_one()
        branch = (
            await session.execute(
                select(BranchModel).where(
                    BranchModel.tenant_id == tenant.id,
                    BranchModel.code == DEMO_BRANCH_CODE,
                )
            )
        ).scalar_one()

        roles = (
            await session.execute(
                select(RoleModel).where(RoleModel.is_global.is_(True))
            )
        ).scalars().all()
        admin_role = next(r for r in roles if r.name == ADMIN_ROLE_NAME)
        staff_role = next((r for r in roles if r.name != ADMIN_ROLE_NAME), admin_role)

        units = await seed_units(session)
        city = await seed_geo(session)
        employees = await seed_staff(
            session, tenant.id, branch.id, staff_role.id, city.id
        )
        cashier = employees["cashier"]
        cook = employees["cook"]

        ingredients = await seed_supplies(session, tenant.id, branch.id, units)
        await seed_inventory_movements(
            session, tenant.id, branch.id, ingredients, cook
        )
        await seed_suppliers(session, tenant.id, ingredients, units)
        await seed_purchase_request(
            session, tenant.id, branch.id, ingredients, units, cashier
        )

        products = await seed_menu(session, tenant.id, branch.id)
        await seed_recipes(session, tenant.id, products, ingredients, units)

        customers = await seed_customers(session, tenant.id, city.id)
        routes = await seed_delivery_routes(session, tenant.id, branch.id, employees)
        tables = await seed_dining_tables(session, tenant.id, branch.id)
        cash_session = await seed_cash_session(session, tenant.id, branch.id, cashier)

        await seed_orders(
            session,
            tenant.id,
            branch.id,
            products,
            tables,
            customers,
            routes,
            cash_session,
            cashier,
        )
        await seed_finance(session, tenant.id, branch.id, cashier)

        await session.commit()

    if counts:
        print("Demo dataset seeded (rows created this run):")
        for table in sorted(counts):
            print(f"  {table:<24} {counts[table]}")
    else:
        print("Demo dataset already present: nothing to create.")


if __name__ == "__main__":
    asyncio.run(seed_demo())
