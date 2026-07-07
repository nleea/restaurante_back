"""Rich demo dataset seed for live testing / pilot rehearsal.

Layers a full operational dataset on top of the minimal baseline created by
``scripts.seed`` (demo tenant ``demo``, branch ``MAIN``, admin user and RBAC).
It fills the cross-module flow end to end so screens and reports are non-empty:

    units / geo -> staff & drivers -> supplies (insumos) -> inventory stock
    -> suppliers / purchasing -> menu, addons & product variants -> recipes (BOM)
    -> recipe details (steps/allergens) -> kitchen stations & product routing
    -> customers -> delivery settings (map pin) / routes / runs
    -> dining tables -> cash sessions (closed + open) -> historical closed orders
    -> live open orders with KDS tickets and geolocated deliveries
    -> finance expense history

The dataset is themed for Riohacha (La Guajira): the delivery map pin sits on
the city center and delivery points fall inside the ring bands.

Idempotent: rows are looked up by a natural key before insert, and the
transactional sample data (orders, runs, cash sessions) is guarded so a second
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
from datetime import UTC, date, datetime, time, timedelta
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
    DeliverySettingModel,
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
from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    OrderItemStationModel,
    ProductStationModel,
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
    RecipeDetailModel,
    RecipeItemModel,
)
from restaurante.modules.staff.infrastructure.models import (
    EmployeeModel,
    PlannedShiftModel,
    ShiftTemplateModel,
)
from restaurante.shared.database import SessionFactory
from restaurante.shared.security.password import Argon2PasswordHasher
from restaurante.shared.tenancy.models import BranchModel, TenantModel
from scripts.seed import DEMO_BRANCH_CODE, DEMO_SLUG
from scripts.seed import seed as seed_baseline

# --- status / value constants (plain strings: no DB enum) ---------------------
RUN_PREPARING = "preparing"
RUN_IN_TRANSIT = "in_transit"
DELIVERY_PENDING = "pending"
DELIVERY_ASSIGNED = "assigned"
DELIVERY_IN_TRANSIT = "in_transit"
DELIVERY_DELIVERED = "delivered"
CHANNEL_DINE_IN = "dine_in"
CHANNEL_DELIVERY = "delivery"
CHANNEL_TAKEOUT = "takeout"
PAY_CASH = "cash"
PAY_NEQUI = "nequi"
PAY_DAVIPLATA = "daviplata"
ORDER_OPEN = "open"
ORDER_CLOSED = "closed"
TICKET_PENDING = "pending"
TICKET_IN_PROGRESS = "in_progress"
TICKET_READY = "ready"
KITCHEN_NONE = "none"
KITCHEN_IN_KITCHEN = "in_kitchen"
KITCHEN_READY = "ready"
DEMO_USER_PASSWORD = "demo1234"

# Business location: Riohacha city center (the delivery map ring center).
BUSINESS_LAT = Decimal("11.5442000")
BUSINESS_LNG = Decimal("-72.9075000")
RING_STEP_KM = Decimal("0.80")

NOW = datetime.now(UTC)

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
    obj = (await session.execute(select(model).filter_by(**filters))).scalar_one_or_none()
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
        unit, _ = await get_or_create(session, UnitOfMeasureModel, name=name, abbreviation=abbr)
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
        name="Riohacha",
        country_id=country.id,
        defaults={"state_province": "La Guajira"},
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
        ("Carlos", "Mendoza", "carlos@demo.com", "CC1001", "cashier"),
        ("Luisa", "Fernández", "luisa@demo.com", "CC1005", "cashier2"),
        ("Camilo", "Brito", "camilo@demo.com", "CC1004", "cook"),
        ("Yeimi", "Epieyú", "yeimi@demo.com", "CC1006", "cook2"),
        ("Diego", "Iguarán", "diego@demo.com", "CC1002", "driver1"),
        ("Daniela", "Pushaina", "daniela@demo.com", "CC1003", "driver2"),
        ("Andrés", "Uriana", "andres@demo.com", "CC1007", "driver3"),
        ("Sofía", "Gámez", "sofia@demo.com", "CC1008", "waiter"),
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


# --- shift scheduling: recurring templates + materialized 90-day horizon -----
# weekdays use 0=Sun..6=Sat (matches the calendar UI). One employee (driver3) is
# left without a template on purpose — an on-call example with only rest days.
SHIFT_PATTERNS: dict[str, tuple[list[int], time, time]] = {
    "cashier": ([1, 2, 3, 4, 5, 6], time(9, 0), time(18, 0)),
    "cashier2": ([1, 2, 3, 4, 5], time(8, 0), time(17, 0)),
    "cook": ([1, 2, 3, 4, 5], time(6, 0), time(15, 0)),
    "cook2": ([3, 4, 5, 6, 0], time(12, 0), time(21, 0)),
    "driver1": ([1, 2, 3, 4, 5], time(10, 0), time(19, 0)),
    "driver2": ([2, 3, 4, 5, 6], time(10, 0), time(19, 0)),
    "waiter": ([1, 2, 3, 4, 5], time(8, 0), time(17, 0)),
}


async def seed_shift_templates(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    employees: dict[str, EmployeeModel],
) -> None:
    today = date.today()
    horizon = today + timedelta(days=90)

    def dow(d: date) -> int:
        return (d.weekday() + 1) % 7

    for key, (weekdays, start, end) in SHIFT_PATTERNS.items():
        emp = employees.get(key)
        if emp is None:
            continue
        await get_or_create(
            session,
            ShiftTemplateModel,
            tenant_id=tenant_id,
            employee_id=emp.id,
            defaults={
                "branch_id": branch_id,
                "weekdays": weekdays,
                "start_time": start,
                "end_time": end,
                "valid_from": today,
                "generated_through": horizon,
            },
        )
        d = today
        while d <= horizon:
            if dow(d) in weekdays:
                await get_or_create(
                    session,
                    PlannedShiftModel,
                    tenant_id=tenant_id,
                    employee_id=emp.id,
                    shift_date=d,
                    defaults={
                        "branch_id": branch_id,
                        "start_time": start,
                        "end_time": end,
                        "status": "scheduled",
                        "origin": "template",
                    },
                )
            d += timedelta(days=1)


# --- supplies (insumos) & inventory ------------------------------------------
# name, unit, current stock, min stock — a few sit below the minimum on purpose
# so the low-stock indicators light up.
INGREDIENTS = [
    # (name, unit, current, min, category)
    ("Carne de res", "kg", Decimal("25.000"), Decimal("5.000"), "Carnes"),
    ("Pechuga de pollo", "kg", Decimal("15.000"), Decimal("4.000"), "Carnes"),
    ("Pan de hamburguesa", "und", Decimal("200.000"), Decimal("40.000"), "Panadería"),
    ("Pan de perro", "und", Decimal("150.000"), Decimal("30.000"), "Panadería"),
    ("Salchicha americana", "und", Decimal("180.000"), Decimal("36.000"), "Carnes"),
    ("Queso cheddar", "kg", Decimal("1.500"), Decimal("2.000"), "Lácteos"),  # below min
    ("Queso costeño", "kg", Decimal("6.000"), Decimal("1.500"), "Lácteos"),
    ("Tocineta", "kg", Decimal("4.000"), Decimal("1.000"), "Carnes"),
    ("Huevo", "und", Decimal("90.000"), Decimal("30.000"), "Lácteos"),
    ("Tomate", "kg", Decimal("12.000"), Decimal("3.000"), "Verduras"),
    ("Lechuga", "kg", Decimal("6.000"), Decimal("1.500"), "Verduras"),
    ("Cebolla", "kg", Decimal("9.000"), Decimal("2.000"), "Verduras"),
    ("Papa", "kg", Decimal("40.000"), Decimal("10.000"), "Verduras"),
    ("Plátano verde", "kg", Decimal("18.000"), Decimal("4.000"), "Verduras"),
    ("Aceite vegetal", "L", Decimal("3.000"), Decimal("4.000"), "Salsas"),  # below min
    ("Arroz", "kg", Decimal("30.000"), Decimal("8.000"), "Granos"),
    ("Camarón", "kg", Decimal("7.000"), Decimal("2.000"), "Pescados"),
    ("Filete de sierra", "kg", Decimal("10.000"), Decimal("3.000"), "Pescados"),
    ("Limón", "kg", Decimal("8.000"), Decimal("2.000"), "Verduras"),
    ("Azúcar", "kg", Decimal("14.000"), Decimal("3.000"), "Granos"),
    ("Sal", "kg", Decimal("10.000"), Decimal("2.000"), "Granos"),
    ("Café molido", "kg", Decimal("3.500"), Decimal("1.000"), "Bebidas"),
    ("Gaseosa lata", "und", Decimal("120.000"), Decimal("24.000"), "Bebidas"),
    ("Salsa de tomate", "L", Decimal("6.000"), Decimal("1.500"), "Salsas"),
    ("Mayonesa", "L", Decimal("5.000"), Decimal("1.500"), "Salsas"),
]


async def seed_supplies(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    units: dict[str, UnitOfMeasureModel],
) -> dict[str, IngredientModel]:
    ingredients: dict[str, IngredientModel] = {}
    for name, unit_abbr, current, minimum, category in INGREDIENTS:
        ingredient, _ = await get_or_create(
            session,
            IngredientModel,
            tenant_id=tenant_id,
            name=name,
            defaults={
                "unit_of_measure_id": units[unit_abbr].id,
                "is_active": True,
                "category": category,
            },
        )
        # Idempotent touch-up: rows created before categories existed get theirs.
        if ingredient.category != category:
            ingredient.category = category
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
    movements = [
        ("in", "purchase", "Carne de res", Decimal("10.000"), "Compra Distribuidora del Caribe"),
        ("in", "purchase", "Papa", Decimal("20.000"), "Compra semanal"),
        ("in", "purchase", "Camarón", Decimal("5.000"), "Compra Pesquera La Guajira"),
        ("in", "purchase", "Pan de hamburguesa", Decimal("100.000"), "Pedido Panadería El Trigal"),
        ("out", "waste", "Lechuga", Decimal("0.800"), "Merma por refrigeración"),
        ("out", "adjustment", "Queso cheddar", Decimal("0.500"), "Ajuste tras conteo físico"),
        ("out", "waste", "Tomate", Decimal("1.200"), "Producto pasado de maduro"),
        ("in", "purchase", "Gaseosa lata", Decimal("48.000"), "Reposición bebidas"),
    ]
    for mtype, reason, name, qty, notes in movements:
        session.add(
            InventoryMovementModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                ingredient_id=ingredients[name].id,
                type=mtype,
                reason=reason,
                quantity=qty,
                employee_id=cook.id,
                notes=notes,
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
        "Distribuidora del Caribe": [
            ("Carne de res", "kg", Decimal("22000.00")),
            ("Pechuga de pollo", "kg", Decimal("12000.00")),
            ("Queso cheddar", "kg", Decimal("18000.00")),
            ("Tocineta", "kg", Decimal("21000.00")),
        ],
        "Panadería El Trigal": [
            ("Pan de hamburguesa", "und", Decimal("700.00")),
            ("Pan de perro", "und", Decimal("600.00")),
        ],
        "Pesquera La Guajira": [
            ("Camarón", "kg", Decimal("38000.00")),
            ("Filete de sierra", "kg", Decimal("26000.00")),
        ],
        "Abarrotes Don Jaime": [
            ("Arroz", "kg", Decimal("4200.00")),
            ("Aceite vegetal", "L", Decimal("9500.00")),
            ("Azúcar", "kg", Decimal("4000.00")),
            ("Salsa de tomate", "L", Decimal("8500.00")),
            ("Gaseosa lata", "und", Decimal("2200.00")),
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


async def seed_purchase_requests(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    ingredients: dict[str, IngredientModel],
    units: dict[str, UnitOfMeasureModel],
    requester: EmployeeModel,
    cook: EmployeeModel,
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
    requests = [
        (
            requester,
            "pending",
            "Reposición semanal de insumos",
            [
                ("Carne de res", Decimal("10.000"), "kg"),
                ("Pan de hamburguesa", Decimal("100.000"), "und"),
                ("Queso cheddar", Decimal("4.000"), "kg"),
                ("Aceite vegetal", Decimal("8.000"), "L"),
            ],
        ),
        (
            cook,
            "approved",
            "Pescado y camarón para fin de semana",
            [
                ("Camarón", Decimal("6.000"), "kg"),
                ("Filete de sierra", Decimal("8.000"), "kg"),
                ("Limón", Decimal("4.000"), "kg"),
            ],
        ),
    ]
    for employee, status, reason, items in requests:
        request = PurchaseRequestModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            requested_by_employee_id=employee.id,
            status=status,
            reason=reason,
        )
        session.add(request)
        await session.flush()
        counts["purchase_requests"] += 1
        for ing_name, qty, unit_abbr in items:
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


# --- menu, addons & recipes ----------------------------------------------------
MENU = [
    (
        "Hamburguesas",
        "Hamburguesa Clásica",
        Decimal("18000.00"),
        "Carne 150g, queso cheddar y vegetales frescos",
    ),
    ("Hamburguesas", "Hamburguesa Doble", Decimal("26000.00"), "Doble carne y doble cheddar"),
    (
        "Hamburguesas",
        "Hamburguesa de Pollo",
        Decimal("20000.00"),
        "Pechuga a la plancha con mayonesa de la casa",
    ),
    (
        "Hamburguesas",
        "Hamburguesa Costeña",
        Decimal("24000.00"),
        "Queso costeño, tocineta y plátano maduro",
    ),
    (
        "Perros Calientes",
        "Perro Clásico",
        Decimal("12000.00"),
        "Salchicha americana, salsas y papitas trituradas",
    ),
    (
        "Perros Calientes",
        "Perro Especial",
        Decimal("16000.00"),
        "Con tocineta, huevo de codorniz y queso",
    ),
    ("Salchipapas", "Salchipapa Sencilla", Decimal("14000.00"), "Para uno, con salsas de la casa"),
    (
        "Salchipapas",
        "Salchipapa Familiar",
        Decimal("28000.00"),
        "Para compartir, con tocineta y queso gratinado",
    ),
    ("Del Mar", "Arroz de Camarón", Decimal("32000.00"), "Camarón guajiro con arroz cremoso"),
    ("Del Mar", "Filete de Sierra", Decimal("30000.00"), "A la plancha con patacones y ensalada"),
    ("Acompañamientos", "Papas Fritas", Decimal("8000.00"), "Porción de papa a la francesa"),
    ("Acompañamientos", "Patacones", Decimal("7000.00"), "Con hogao y queso costeño rallado"),
    ("Bebidas", "Gaseosa Lata", Decimal("5000.00"), "330 ml, bien fría"),
    ("Bebidas", "Limonada Natural", Decimal("6000.00"), "Limón exprimido al momento"),
    ("Bebidas", "Café Tinto", Decimal("2500.00"), "Café de la Sierra Nevada"),
    ("Postres", "Brownie con Helado", Decimal("9000.00"), "Brownie tibio con helado de vainilla"),
]

ADDONS = [
    ("Tocineta extra", Decimal("3000.00")),
    ("Queso extra", Decimal("2500.00")),
    ("Huevo frito", Decimal("2000.00")),
]
# addon name -> product names it applies to
ADDON_PRODUCTS = {
    "Tocineta extra": [
        "Hamburguesa Clásica",
        "Hamburguesa Doble",
        "Hamburguesa de Pollo",
        "Perro Clásico",
        "Salchipapa Sencilla",
    ],
    "Queso extra": [
        "Hamburguesa Clásica",
        "Hamburguesa Doble",
        "Hamburguesa Costeña",
        "Perro Clásico",
        "Perro Especial",
    ],
    "Huevo frito": [
        "Hamburguesa Clásica",
        "Perro Clásico",
        "Salchipapa Sencilla",
        "Salchipapa Familiar",
    ],
}

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
    "Hamburguesa de Pollo": [
        ("Pechuga de pollo", Decimal("0.180"), "kg"),
        ("Pan de hamburguesa", Decimal("1.000"), "und"),
        ("Lechuga", Decimal("0.015"), "kg"),
        ("Mayonesa", Decimal("0.020"), "L"),
    ],
    "Hamburguesa Costeña": [
        ("Carne de res", Decimal("0.150"), "kg"),
        ("Pan de hamburguesa", Decimal("1.000"), "und"),
        ("Queso costeño", Decimal("0.040"), "kg"),
        ("Tocineta", Decimal("0.030"), "kg"),
        ("Plátano verde", Decimal("0.080"), "kg"),
    ],
    "Perro Clásico": [
        ("Salchicha americana", Decimal("1.000"), "und"),
        ("Pan de perro", Decimal("1.000"), "und"),
        ("Salsa de tomate", Decimal("0.015"), "L"),
        ("Mayonesa", Decimal("0.015"), "L"),
    ],
    "Perro Especial": [
        ("Salchicha americana", Decimal("1.000"), "und"),
        ("Pan de perro", Decimal("1.000"), "und"),
        ("Tocineta", Decimal("0.025"), "kg"),
        ("Huevo", Decimal("2.000"), "und"),
        ("Queso costeño", Decimal("0.025"), "kg"),
    ],
    "Salchipapa Sencilla": [
        ("Papa", Decimal("0.300"), "kg"),
        ("Salchicha americana", Decimal("2.000"), "und"),
        ("Aceite vegetal", Decimal("0.060"), "L"),
        ("Sal", Decimal("0.005"), "kg"),
    ],
    "Salchipapa Familiar": [
        ("Papa", Decimal("0.700"), "kg"),
        ("Salchicha americana", Decimal("5.000"), "und"),
        ("Tocineta", Decimal("0.060"), "kg"),
        ("Queso cheddar", Decimal("0.080"), "kg"),
        ("Aceite vegetal", Decimal("0.120"), "L"),
    ],
    "Arroz de Camarón": [
        ("Arroz", Decimal("0.200"), "kg"),
        ("Camarón", Decimal("0.180"), "kg"),
        ("Cebolla", Decimal("0.040"), "kg"),
        ("Tomate", Decimal("0.040"), "kg"),
    ],
    "Filete de Sierra": [
        ("Filete de sierra", Decimal("0.250"), "kg"),
        ("Plátano verde", Decimal("0.200"), "kg"),
        ("Limón", Decimal("0.030"), "kg"),
        ("Lechuga", Decimal("0.020"), "kg"),
    ],
    "Papas Fritas": [
        ("Papa", Decimal("0.250"), "kg"),
        ("Aceite vegetal", Decimal("0.050"), "L"),
        ("Sal", Decimal("0.005"), "kg"),
    ],
    "Patacones": [
        ("Plátano verde", Decimal("0.250"), "kg"),
        ("Queso costeño", Decimal("0.020"), "kg"),
        ("Aceite vegetal", Decimal("0.040"), "L"),
    ],
    "Limonada Natural": [
        ("Limón", Decimal("0.080"), "kg"),
        ("Azúcar", Decimal("0.030"), "kg"),
    ],
    "Café Tinto": [
        ("Café molido", Decimal("0.010"), "kg"),
        ("Azúcar", Decimal("0.008"), "kg"),
    ],
    "Gaseosa Lata": [
        ("Gaseosa lata", Decimal("1.000"), "und"),
    ],
}

# product name -> (steps, allergens) for the KDS recipe card drawer.
RECIPE_DETAILS = {
    "Hamburguesa Clásica": (
        [
            "Sellar la carne 3 min por lado en la parrilla",
            "Fundir el cheddar sobre la carne al final",
            "Tostar el pan con mantequilla",
            "Armar: base, carne, queso, tomate, lechuga, tapa",
        ],
        ["gluten", "dairy"],
    ),
    "Hamburguesa Costeña": (
        [
            "Sellar la carne 3 min por lado",
            "Dorar la tocineta hasta quedar crocante",
            "Freír tajadas de maduro",
            "Armar con queso costeño rallado por encima",
        ],
        ["gluten", "dairy"],
    ),
    "Perro Especial": (
        [
            "Cocinar la salchicha en agua y luego dorar en plancha",
            "Freír los huevos de codorniz",
            "Armar: pan, salchicha, tocineta, huevo, queso y salsas",
        ],
        ["gluten", "dairy"],
    ),
    "Salchipapa Familiar": (
        [
            "Freír la papa a 180°C hasta dorar",
            "Dorar salchicha en rodajas y tocineta",
            "Servir en bandeja, gratinar el queso por encima",
        ],
        ["dairy"],
    ),
    "Arroz de Camarón": (
        [
            "Sofreír cebolla y tomate",
            "Agregar el camarón y sellar 2 min",
            "Incorporar el arroz y el caldo, cocinar 15 min",
            "Rectificar sal y servir con limón",
        ],
        ["shellfish"],
    ),
    "Filete de Sierra": (
        [
            "Marinar el filete con limón y sal 10 min",
            "Plancha 4 min por lado",
            "Freír los patacones y aplastar",
            "Servir con ensalada fresca",
        ],
        [],
    ),
}


async def seed_menu(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
) -> dict[str, dict[str, Any]]:
    """Returns product name -> {product, variant, price}."""
    products: dict[str, dict[str, Any]] = {}
    for cat_name, prod_name, price, description in MENU:
        category, _ = await get_or_create(
            session, CategoryModel, tenant_id=tenant_id, name=cat_name
        )
        product, _ = await get_or_create(
            session,
            ProductModel,
            tenant_id=tenant_id,
            name=prod_name,
            defaults={
                "category_id": category.id,
                "description": description,
                "is_active": True,
            },
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
        products[prod_name] = {"product": product, "variant": variant, "price": price}
    return products


async def seed_addons(
    session: AsyncSession,
    tenant_id: Any,
    products: dict[str, dict[str, Any]],
) -> None:
    for name, price in ADDONS:
        addon, _ = await get_or_create(
            session,
            AddonModel,
            tenant_id=tenant_id,
            name=name,
            defaults={"price": price, "is_active": True},
        )
        for prod_name in ADDON_PRODUCTS[name]:
            await get_or_create(
                session,
                ProductAddonModel,
                tenant_id=tenant_id,
                product_id=products[prod_name]["product"].id,
                addon_id=addon.id,
            )


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
    for prod_name, (steps, allergens) in RECIPE_DETAILS.items():
        await get_or_create(
            session,
            RecipeDetailModel,
            tenant_id=tenant_id,
            product_variant_id=products[prod_name]["variant"].id,
            defaults={"steps": steps, "allergens": allergens},
        )


# --- kitchen (KDS): stations & product routing ---------------------------------
STATIONS = ["Parrilla", "Freidora", "Plancha", "Ensamble", "Bebidas"]

# product name -> [(station, role, tasks)]
PRODUCT_STATIONS = {
    "Hamburguesa Clásica": [
        ("Parrilla", "Carne", ["Carne 150g", "Fundir cheddar"]),
        ("Ensamble", None, ["Tostar pan", "Vegetales", "Armar"]),
    ],
    "Hamburguesa Doble": [
        ("Parrilla", "Carne", ["Doble carne 300g", "Doble cheddar"]),
        ("Ensamble", None, ["Tostar pan", "Armar"]),
    ],
    "Hamburguesa de Pollo": [
        ("Plancha", "Pollo", ["Pechuga a la plancha"]),
        ("Ensamble", None, ["Tostar pan", "Mayonesa de la casa", "Armar"]),
    ],
    "Hamburguesa Costeña": [
        ("Parrilla", "Carne", ["Carne 150g", "Tocineta crocante"]),
        ("Freidora", None, ["Tajadas de maduro"]),
        ("Ensamble", None, ["Queso costeño", "Armar"]),
    ],
    "Perro Clásico": [
        ("Plancha", None, ["Dorar salchicha"]),
        ("Ensamble", None, ["Salsas", "Papitas trituradas"]),
    ],
    "Perro Especial": [
        ("Plancha", None, ["Dorar salchicha", "Huevos de codorniz"]),
        ("Ensamble", None, ["Tocineta", "Queso", "Armar"]),
    ],
    "Salchipapa Sencilla": [
        ("Freidora", None, ["Freír papa", "Salchicha en rodajas"]),
    ],
    "Salchipapa Familiar": [
        ("Freidora", None, ["Freír papa doble", "Salchicha y tocineta"]),
        ("Ensamble", None, ["Gratinar queso", "Emplatar bandeja"]),
    ],
    "Arroz de Camarón": [
        ("Plancha", "Del mar", ["Sofrito", "Sellar camarón", "Arroz cremoso"]),
    ],
    "Filete de Sierra": [
        ("Plancha", "Del mar", ["Filete 4 min por lado"]),
        ("Freidora", None, ["Patacones"]),
    ],
    "Papas Fritas": [
        ("Freidora", None, ["Freír porción"]),
    ],
    "Patacones": [
        ("Freidora", None, ["Freír y aplastar", "Queso rallado"]),
    ],
    "Limonada Natural": [
        ("Bebidas", None, ["Exprimir limón", "Servir con hielo"]),
    ],
    "Café Tinto": [
        ("Bebidas", None, ["Preparar tinto"]),
    ],
    "Gaseosa Lata": [
        ("Bebidas", None, ["Servir fría"]),
    ],
    "Brownie con Helado": [
        ("Ensamble", None, ["Calentar brownie", "Bola de helado"]),
    ],
}


async def seed_kitchen(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    products: dict[str, dict[str, Any]],
) -> dict[str, KitchenStationModel]:
    stations: dict[str, KitchenStationModel] = {}
    for position, name in enumerate(STATIONS):
        station, _ = await get_or_create(
            session,
            KitchenStationModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            name=name,
            defaults={"position": position, "is_active": True},
        )
        stations[name] = station
    for prod_name, mappings in PRODUCT_STATIONS.items():
        for station_name, role, tasks in mappings:
            await get_or_create(
                session,
                ProductStationModel,
                tenant_id=tenant_id,
                product_id=products[prod_name]["product"].id,
                kitchen_station_id=stations[station_name].id,
                defaults={"role": role, "tasks": tasks},
            )
    return stations


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
        ("Luis", "Ojeda", "CC2004", "3004445566"),
        ("Carmen", "Freyle", "CC2005", "3005556677"),
        ("Rafael", "Ipuana", "CC2006", "3006667788"),
        ("Paola", "Barros", "CC2007", "3007778899"),
        ("Jorge", "Cotes", "CC2008", "3008889900"),
        ("Milena", "Arpushana", "CC2009", "3009990011"),
        ("Edgar", "Solano", "CC2010", "3010001122"),
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


# --- delivery: settings (map pin), routes (rings), runs ------------------------
async def seed_delivery_settings(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
) -> None:
    await get_or_create(
        session,
        DeliverySettingModel,
        tenant_id=tenant_id,
        branch_id=branch_id,
        defaults={
            "latitude": BUSINESS_LAT,
            "longitude": BUSINESS_LNG,
            "ring_step_km": RING_STEP_KM,
        },
    )


async def seed_delivery_routes(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    employees: dict[str, EmployeeModel],
) -> dict[str, dict[str, Any]]:
    """Returns route name -> {route, run, driver}. Rings ordered by position."""
    config = [
        # name, zones, position, active, driver key, run status
        ("Anillo Centro", ["Centro", "Arriba", "El Progreso"], 0, True, "driver1", RUN_PREPARING),
        (
            "Anillo Medio",
            ["Cooperativo", "Los Almendros", "Padilla"],
            1,
            True,
            "driver2",
            RUN_IN_TRANSIT,
        ),
        (
            "Anillo Extendido",
            ["Villa Fátima", "La Esperanza", "Camino Verde"],
            2,
            True,
            "driver3",
            None,
        ),
        ("Ruta Aeropuerto", ["Aeropuerto Almirante Padilla"], 3, False, None, None),
    ]
    routes: dict[str, dict[str, Any]] = {}
    for name, zones, position, active, driver_key, run_status in config:
        route, _ = await get_or_create(
            session,
            DeliveryRouteModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            name=name,
            defaults={"zones": zones, "position": position, "is_active": active},
        )
        driver = employees[driver_key] if driver_key else None
        run = None
        if driver is not None:
            await get_or_create(
                session,
                DeliveryRouteDriverModel,
                tenant_id=tenant_id,
                delivery_route_id=route.id,
                employee_id=driver.id,
                defaults={"is_active": True},
            )
        if driver is not None and run_status is not None:
            defaults: dict[str, Any] = {}
            if run_status == RUN_IN_TRANSIT:
                defaults["departed_at"] = NOW - timedelta(minutes=25)
            run, _ = await get_or_create(
                session,
                DeliveryRunModel,
                tenant_id=tenant_id,
                delivery_route_id=route.id,
                employee_id=driver.id,
                status=run_status,
                defaults=defaults,
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
    capacities = [2, 4, 4, 4, 6, 6, 8, 2]
    for number, capacity in zip([str(n) for n in range(1, 9)], capacities, strict=True):
        table, _ = await get_or_create(
            session,
            DiningTableModel,
            tenant_id=tenant_id,
            branch_id=branch_id,
            number=number,
            defaults={"capacity": capacity, "status": "free", "is_active": True},
        )
        tables.append(table)
    return tables


# --- cash sessions --------------------------------------------------------------
async def seed_cash_sessions(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    cashier: EmployeeModel,
    cashier2: EmployeeModel,
) -> tuple[CashSessionModel, CashSessionModel]:
    """Returns (closed historical session, open current session)."""
    closed = (
        (
            await session.execute(
                select(CashSessionModel).where(
                    CashSessionModel.branch_id == branch_id,
                    CashSessionModel.status == "closed",
                )
            )
        )
        .scalars()
        .first()
    )
    if closed is None:
        closed = CashSessionModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            opened_by_employee_id=cashier2.id,
            closed_by_employee_id=cashier2.id,
            opening_amount=Decimal("150000.00"),
            expected_amount=Decimal("612000.00"),
            counted_amount=Decimal("607000.00"),
            difference=Decimal("-5000.00"),
            status="closed",
            opened_at=NOW - timedelta(days=1, hours=12),
            closed_at=NOW - timedelta(days=1, hours=1),
        )
        session.add(closed)
        await session.flush()
        counts["cash_sessions"] += 1
        session.add(
            CashMovementModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                cash_session_id=closed.id,
                type="in",
                concept="Apertura de caja",
                amount=Decimal("150000.00"),
                method=PAY_CASH,
            )
        )
        counts["cash_movements"] += 1

    opened = (
        (
            await session.execute(
                select(CashSessionModel).where(
                    CashSessionModel.branch_id == branch_id,
                    CashSessionModel.status == "open",
                )
            )
        )
        .scalars()
        .first()
    )
    if opened is None:
        opened = CashSessionModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            opened_by_employee_id=cashier.id,
            opening_amount=Decimal("200000.00"),
            status="open",
            opened_at=NOW - timedelta(hours=5),
        )
        session.add(opened)
        await session.flush()
        counts["cash_sessions"] += 1
        for mtype, concept, amount in [
            ("in", "Apertura de caja", Decimal("200000.00")),
            ("out", "Compra de hielo", Decimal("20000.00")),
        ]:
            session.add(
                CashMovementModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    cash_session_id=opened.id,
                    type=mtype,
                    concept=concept,
                    amount=amount,
                    method=PAY_CASH,
                )
            )
            counts["cash_movements"] += 1
    return closed, opened


# --- orders: historical closed + live open with KDS tickets & deliveries -------
# Historical plan: (days ago, hour, channel, items, pay, table idx?, customer idx?)
HISTORY_PLAN: list[dict[str, Any]] = [
    {
        "days": 7,
        "hour": 12,
        "channel": CHANNEL_DINE_IN,
        "items": [("Hamburguesa Clásica", 2), ("Gaseosa Lata", 2)],
        "pay": PAY_CASH,
        "table": 0,
    },
    {
        "days": 7,
        "hour": 19,
        "channel": CHANNEL_DELIVERY,
        "items": [("Salchipapa Familiar", 1)],
        "pay": PAY_NEQUI,
        "customer": 0,
        "address": "Cra 7 # 12-34, Centro",
        "zone": "Centro",
        "lat": "11.5461",
        "lng": "-72.9081",
    },
    {
        "days": 6,
        "hour": 13,
        "channel": CHANNEL_DINE_IN,
        "items": [("Arroz de Camarón", 2), ("Limonada Natural", 2)],
        "pay": PAY_CASH,
        "table": 2,
    },
    {
        "days": 6,
        "hour": 20,
        "channel": CHANNEL_TAKEOUT,
        "items": [("Perro Especial", 3)],
        "pay": PAY_DAVIPLATA,
    },
    {
        "days": 5,
        "hour": 12,
        "channel": CHANNEL_DINE_IN,
        "items": [("Filete de Sierra", 1), ("Patacones", 1), ("Limonada Natural", 1)],
        "pay": PAY_NEQUI,
        "table": 4,
    },
    {
        "days": 5,
        "hour": 19,
        "channel": CHANNEL_DELIVERY,
        "items": [("Hamburguesa Doble", 2), ("Gaseosa Lata", 2)],
        "pay": PAY_CASH,
        "customer": 1,
        "address": "Cll 14 # 8-20, Cooperativo",
        "zone": "Cooperativo",
        "lat": "11.5388",
        "lng": "-72.9145",
    },
    {
        "days": 4,
        "hour": 13,
        "channel": CHANNEL_DINE_IN,
        "items": [("Hamburguesa Costeña", 2), ("Papas Fritas", 1), ("Gaseosa Lata", 2)],
        "pay": PAY_CASH,
        "table": 1,
    },
    {
        "days": 4,
        "hour": 20,
        "channel": CHANNEL_DELIVERY,
        "items": [("Salchipapa Sencilla", 2)],
        "pay": PAY_NEQUI,
        "customer": 2,
        "address": "Cll 15 # 11-52, Padilla",
        "zone": "Padilla",
        "lat": "11.5379",
        "lng": "-72.9022",
    },
    {
        "days": 3,
        "hour": 12,
        "channel": CHANNEL_TAKEOUT,
        "items": [("Arroz de Camarón", 1), ("Café Tinto", 1)],
        "pay": PAY_CASH,
    },
    {
        "days": 3,
        "hour": 19,
        "channel": CHANNEL_DINE_IN,
        "items": [("Perro Clásico", 4), ("Gaseosa Lata", 4)],
        "pay": PAY_DAVIPLATA,
        "table": 5,
    },
    {
        "days": 3,
        "hour": 21,
        "channel": CHANNEL_DELIVERY,
        "items": [("Hamburguesa Clásica", 3)],
        "pay": PAY_CASH,
        "customer": 3,
        "address": "Cra 15 # 14-05, Los Almendros",
        "zone": "Los Almendros",
        "lat": "11.5350",
        "lng": "-72.9120",
    },
    {
        "days": 2,
        "hour": 13,
        "channel": CHANNEL_DINE_IN,
        "items": [("Filete de Sierra", 2), ("Limonada Natural", 2), ("Brownie con Helado", 2)],
        "pay": PAY_NEQUI,
        "table": 6,
    },
    {
        "days": 2,
        "hour": 20,
        "channel": CHANNEL_DELIVERY,
        "items": [("Salchipapa Familiar", 1), ("Gaseosa Lata", 3)],
        "pay": PAY_CASH,
        "customer": 4,
        "address": "Cll 34 # 7-19, Villa Fátima",
        "zone": "Villa Fátima",
        "lat": "11.5265",
        "lng": "-72.9040",
    },
    {
        "days": 1,
        "hour": 12,
        "channel": CHANNEL_DINE_IN,
        "items": [("Hamburguesa de Pollo", 2), ("Papas Fritas", 2), ("Gaseosa Lata", 2)],
        "pay": PAY_CASH,
        "table": 3,
    },
    {
        "days": 1,
        "hour": 14,
        "channel": CHANNEL_TAKEOUT,
        "items": [("Patacones", 2), ("Café Tinto", 2)],
        "pay": PAY_CASH,
    },
    {
        "days": 1,
        "hour": 19,
        "channel": CHANNEL_DELIVERY,
        "items": [("Perro Especial", 2), ("Gaseosa Lata", 2)],
        "pay": PAY_NEQUI,
        "customer": 5,
        "address": "Cra 9 # 13-44, Arriba",
        "zone": "Arriba",
        "lat": "11.5470",
        "lng": "-72.9042",
    },
    {
        "days": 1,
        "hour": 20,
        "channel": CHANNEL_DINE_IN,
        "items": [("Hamburguesa Doble", 1), ("Hamburguesa Clásica", 1), ("Gaseosa Lata", 2)],
        "pay": PAY_CASH,
        "table": 7,
    },
    {
        "days": 1,
        "hour": 21,
        "channel": CHANNEL_DELIVERY,
        "items": [("Arroz de Camarón", 2)],
        "pay": PAY_DAVIPLATA,
        "customer": 6,
        "address": "Cll 12 # 6-80, El Progreso",
        "zone": "El Progreso",
        "lat": "11.5432",
        "lng": "-72.9130",
    },
]

# Live plan: open orders visible right now on tables / KDS / delivery map.
# ticket status per station is listed explicitly.
LIVE_PLAN: list[dict[str, Any]] = [
    {
        "channel": CHANNEL_DINE_IN,
        "table": 1,
        "items": [("Hamburguesa Costeña", 2), ("Limonada Natural", 2)],
        "tickets": {"Hamburguesa Costeña": TICKET_IN_PROGRESS, "Limonada Natural": TICKET_READY},
        "minutes_ago": 12,
    },
    {
        "channel": CHANNEL_DINE_IN,
        "table": 4,
        "items": [("Salchipapa Familiar", 1), ("Gaseosa Lata", 3)],
        "tickets": {"Salchipapa Familiar": TICKET_PENDING, "Gaseosa Lata": TICKET_PENDING},
        "minutes_ago": 5,
    },
    {
        "channel": CHANNEL_TAKEOUT,
        "items": [("Arroz de Camarón", 1)],
        "tickets": {"Arroz de Camarón": TICKET_READY},
        "pay": PAY_NEQUI,
        "minutes_ago": 30,
    },
    {
        "channel": CHANNEL_DELIVERY,
        "items": [("Hamburguesa Clásica", 1), ("Papas Fritas", 1)],
        "tickets": {"Hamburguesa Clásica": TICKET_IN_PROGRESS, "Papas Fritas": TICKET_PENDING},
        "customer": 7,
        "delivery_status": DELIVERY_PENDING,
        "address": "Cra 8 # 11-25, Centro",
        "zone": "Centro",
        "lat": "11.5410",
        "lng": "-72.9058",
        "minutes_ago": 8,
    },
    {
        "channel": CHANNEL_DELIVERY,
        "items": [("Hamburguesa Doble", 2), ("Gaseosa Lata", 2)],
        "tickets": {"Hamburguesa Doble": TICKET_READY, "Gaseosa Lata": TICKET_READY},
        "customer": 8,
        "delivery_status": DELIVERY_ASSIGNED,
        "route": "Anillo Centro",
        "address": "Cll 13 # 9-14, El Progreso",
        "zone": "El Progreso",
        "lat": "11.5455",
        "lng": "-72.9118",
        "minutes_ago": 22,
    },
    {
        "channel": CHANNEL_DELIVERY,
        "items": [("Salchipapa Familiar", 1), ("Gaseosa Lata", 2)],
        "tickets": {"Salchipapa Familiar": TICKET_READY, "Gaseosa Lata": TICKET_READY},
        "customer": 9,
        "delivery_status": DELIVERY_IN_TRANSIT,
        "route": "Anillo Medio",
        "address": "Cll 15 # 14-33, Cooperativo",
        "zone": "Cooperativo",
        "lat": "11.5361",
        "lng": "-72.9151",
        "minutes_ago": 40,
    },
    {
        "channel": CHANNEL_DELIVERY,
        "items": [("Perro Especial", 3)],
        "tickets": {"Perro Especial": TICKET_READY},
        "customer": 2,
        "delivery_status": DELIVERY_DELIVERED,
        "route": "Anillo Medio",
        "pay": PAY_CASH,
        "address": "Cra 12A # 14-70, Los Almendros",
        "zone": "Los Almendros",
        "lat": "11.5341",
        "lng": "-72.9101",
        "minutes_ago": 75,
    },
]


def _derive_kitchen_state(statuses: list[str]) -> str:
    if not statuses:
        return KITCHEN_NONE
    if all(s == TICKET_READY for s in statuses):
        return KITCHEN_READY
    return KITCHEN_IN_KITCHEN


async def _create_order(
    session: AsyncSession,
    *,
    tenant_id: Any,
    branch_id: Any,
    entry: dict[str, Any],
    created_at: datetime,
    status: str,
    kitchen_state: str,
    products: dict[str, dict[str, Any]],
    tables: list[DiningTableModel],
    customers: list[CustomerModel],
    employee: EmployeeModel,
) -> tuple[OrderModel, list[OrderItemModel], Decimal]:
    order = OrderModel(
        tenant_id=tenant_id,
        branch_id=branch_id,
        channel=entry["channel"],
        dining_table_id=tables[entry["table"]].id if "table" in entry else None,
        customer_id=customers[entry["customer"]].id if "customer" in entry else None,
        employee_id=employee.id,
        status=status,
        kitchen_state=kitchen_state,
        subtotal=Decimal("0.00"),
        discount=Decimal("0.00"),
        total=Decimal("0.00"),
        created_at=created_at,
        closed_at=created_at + timedelta(minutes=50) if status == ORDER_CLOSED else None,
    )
    session.add(order)
    await session.flush()
    counts["orders"] += 1

    items: list[OrderItemModel] = []
    subtotal = Decimal("0.00")
    for prod_name, qty in entry["items"]:
        price = products[prod_name]["price"]
        line_subtotal = price * qty
        subtotal += line_subtotal
        item = OrderItemModel(
            tenant_id=tenant_id,
            branch_id=branch_id,
            order_id=order.id,
            product_variant_id=products[prod_name]["variant"].id,
            quantity=qty,
            unit_price=price,
            line_subtotal=line_subtotal,
            status="pending",
            created_at=created_at,
        )
        session.add(item)
        items.append(item)
        counts["order_items"] += 1
    await session.flush()

    order.subtotal = subtotal
    order.total = subtotal
    return order, items, subtotal


async def seed_orders(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    products: dict[str, dict[str, Any]],
    tables: list[DiningTableModel],
    customers: list[CustomerModel],
    routes: dict[str, dict[str, Any]],
    stations: dict[str, KitchenStationModel],
    closed_session: CashSessionModel,
    open_session: CashSessionModel,
    cashier: EmployeeModel,
    waiter: EmployeeModel,
) -> None:
    existing = (
        await session.execute(
            select(func.count()).select_from(OrderModel).where(OrderModel.branch_id == branch_id)
        )
    ).scalar_one()
    if existing:
        return

    # -- historical closed orders (reports, cash history, top products) --------
    for entry in HISTORY_PLAN:
        created_at = (NOW - timedelta(days=entry["days"])).replace(
            hour=entry["hour"], minute=15, second=0, microsecond=0
        )
        order, _items, subtotal = await _create_order(
            session,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entry=entry,
            created_at=created_at,
            status=ORDER_CLOSED,
            kitchen_state=KITCHEN_READY,
            products=products,
            tables=tables,
            customers=customers,
            employee=cashier,
        )
        session.add(
            OrderPaymentModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                order_id=order.id,
                cash_session_id=closed_session.id,
                amount=subtotal,
                method=entry["pay"],
                employee_id=cashier.id,
                created_at=order.closed_at,
            )
        )
        counts["order_payments"] += 1
        if entry["channel"] == CHANNEL_DELIVERY:
            session.add(
                OrderDeliveryModel(
                    tenant_id=tenant_id,
                    order_id=order.id,
                    address_text=entry["address"],
                    neighborhood=entry["zone"],
                    latitude=Decimal(entry["lat"]),
                    longitude=Decimal(entry["lng"]),
                    delivery_status=DELIVERY_DELIVERED,
                    delivered_at=order.closed_at,
                )
            )
            counts["order_deliveries"] += 1

    # -- live open orders (tables, KDS tickets, delivery map overlay) ----------
    route_position: Counter[str] = Counter()
    for entry in LIVE_PLAN:
        created_at = NOW - timedelta(minutes=entry["minutes_ago"])
        ticket_statuses = [
            entry["tickets"][prod_name]
            for prod_name, _qty in entry["items"]
            for _mapping in PRODUCT_STATIONS.get(prod_name, [])
        ]
        order, items, subtotal = await _create_order(
            session,
            tenant_id=tenant_id,
            branch_id=branch_id,
            entry=entry,
            created_at=created_at,
            status=ORDER_OPEN,
            kitchen_state=_derive_kitchen_state(ticket_statuses),
            products=products,
            tables=tables,
            customers=customers,
            employee=waiter,
        )
        if "table" in entry:
            tables[entry["table"]].status = "occupied"

        # KDS tickets: fan each item out to its product's stations.
        for item, (prod_name, _qty) in zip(items, entry["items"], strict=True):
            ticket_status = entry["tickets"][prod_name]
            for station_name, role, tasks in PRODUCT_STATIONS.get(prod_name, []):
                session.add(
                    OrderItemStationModel(
                        tenant_id=tenant_id,
                        branch_id=branch_id,
                        order_item_id=item.id,
                        kitchen_station_id=stations[station_name].id,
                        status=ticket_status,
                        role=role,
                        tasks=tasks,
                        entered_at=created_at,
                        ready_at=(
                            created_at + timedelta(minutes=10)
                            if ticket_status == TICKET_READY
                            else None
                        ),
                    )
                )
                counts["order_item_stations"] += 1

        if "pay" in entry:
            session.add(
                OrderPaymentModel(
                    tenant_id=tenant_id,
                    branch_id=branch_id,
                    order_id=order.id,
                    cash_session_id=open_session.id,
                    amount=subtotal,
                    method=entry["pay"],
                    employee_id=cashier.id,
                )
            )
            counts["order_payments"] += 1

        if entry["channel"] == CHANNEL_DELIVERY:
            status = entry["delivery_status"]
            route_info = routes.get(entry.get("route", ""), None)
            assigned = status != DELIVERY_PENDING and route_info is not None
            position = None
            if assigned:
                route_position[entry["route"]] += 1
                position = route_position[entry["route"]]
            session.add(
                OrderDeliveryModel(
                    tenant_id=tenant_id,
                    order_id=order.id,
                    delivery_route_id=route_info["route"].id if route_info else None,
                    delivery_run_id=(
                        route_info["run"].id
                        if assigned and route_info and route_info["run"]
                        else None
                    ),
                    address_text=entry["address"],
                    neighborhood=entry["zone"],
                    latitude=Decimal(entry["lat"]),
                    longitude=Decimal(entry["lng"]),
                    delivery_status=status,
                    route_position=position,
                    delivered_at=(
                        NOW - timedelta(minutes=10) if status == DELIVERY_DELIVERED else None
                    ),
                )
            )
            counts["order_deliveries"] += 1


# --- finance ------------------------------------------------------------------
EXPENSES = [
    ("Servicios", "Energía eléctrica", Decimal("450000.00"), 5),
    ("Servicios", "Gas natural", Decimal("180000.00"), 12),
    ("Servicios", "Acueducto y alcantarillado", Decimal("120000.00"), 8),
    ("Servicios", "Internet y telefonía", Decimal("110000.00"), 15),
    ("Arriendo", "Arriendo del local", Decimal("1800000.00"), 28),
    ("Mantenimiento", "Reparación de nevera", Decimal("250000.00"), 10),
    ("Mantenimiento", "Recarga de extintores", Decimal("90000.00"), 20),
    ("Insumos varios", "Desechables y empaques", Decimal("160000.00"), 6),
    ("Insumos varios", "Productos de aseo", Decimal("85000.00"), 4),
    ("Nómina", "Anticipo de nómina", Decimal("600000.00"), 14),
]


async def seed_finance(
    session: AsyncSession,
    tenant_id: Any,
    branch_id: Any,
    cashier: EmployeeModel,
) -> None:
    categories: dict[str, ExpenseCategoryModel] = {}
    for cat_name in {c for c, *_ in EXPENSES}:
        category, _ = await get_or_create(
            session,
            ExpenseCategoryModel,
            tenant_id=tenant_id,
            name=cat_name,
            defaults={"is_active": True},
        )
        categories[cat_name] = category
    existing = (
        await session.execute(
            select(func.count())
            .select_from(ExpenseModel)
            .where(ExpenseModel.branch_id == branch_id)
        )
    ).scalar_one()
    if existing:
        return
    for cat_name, description, amount, days_ago in EXPENSES:
        session.add(
            ExpenseModel(
                tenant_id=tenant_id,
                branch_id=branch_id,
                expense_category_id=categories[cat_name].id,
                description=description,
                amount=amount,
                employee_id=cashier.id,
                incurred_at=NOW - timedelta(days=days_ago),
            )
        )
        counts["expenses"] += 1


# --- orchestrator -------------------------------------------------------------
async def seed_demo() -> None:
    # 1. Guarantee the baseline (tenant/branch/admin/RBAC) exists and is committed.
    await seed_baseline()

    async with SessionFactory() as session:
        tenant = (
            await session.execute(select(TenantModel).where(TenantModel.slug == DEMO_SLUG))
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
            (await session.execute(select(RoleModel).where(RoleModel.is_global.is_(True))))
            .scalars()
            .all()
        )
        admin_role = next(r for r in roles if r.name == ADMIN_ROLE_NAME)
        staff_role = next((r for r in roles if r.name != ADMIN_ROLE_NAME), admin_role)

        units = await seed_units(session)
        city = await seed_geo(session)
        employees = await seed_staff(session, tenant.id, branch.id, staff_role.id, city.id)
        await seed_shift_templates(session, tenant.id, branch.id, employees)
        cashier = employees["cashier"]
        cashier2 = employees["cashier2"]
        cook = employees["cook"]
        waiter = employees["waiter"]

        ingredients = await seed_supplies(session, tenant.id, branch.id, units)
        await seed_inventory_movements(session, tenant.id, branch.id, ingredients, cook)
        await seed_suppliers(session, tenant.id, ingredients, units)
        await seed_purchase_requests(
            session, tenant.id, branch.id, ingredients, units, cashier, cook
        )

        products = await seed_menu(session, tenant.id, branch.id)
        await seed_addons(session, tenant.id, products)
        await seed_recipes(session, tenant.id, products, ingredients, units)
        stations = await seed_kitchen(session, tenant.id, branch.id, products)

        customers = await seed_customers(session, tenant.id, city.id)
        await seed_delivery_settings(session, tenant.id, branch.id)
        routes = await seed_delivery_routes(session, tenant.id, branch.id, employees)
        tables = await seed_dining_tables(session, tenant.id, branch.id)
        closed_session, open_session = await seed_cash_sessions(
            session, tenant.id, branch.id, cashier, cashier2
        )

        await seed_orders(
            session,
            tenant.id,
            branch.id,
            products,
            tables,
            customers,
            routes,
            stations,
            closed_session,
            open_session,
            cashier,
            waiter,
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
