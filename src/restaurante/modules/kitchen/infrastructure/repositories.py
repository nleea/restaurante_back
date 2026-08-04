"""Persistence adapter for the Kitchen module over SQLAlchemy async.

Each write commits its own unit of work and filters explicitly by ``tenant_id``
(and ``branch_id`` where applicable). Reads into menu/orders tables support
routing an order's items to stations.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.infrastructure.models import CashSessionModel
from restaurante.modules.catalog.infrastructure.models import UnitOfMeasureModel
from restaurante.modules.kitchen.domain.amounts import SubUnit, format_amount
from restaurante.modules.kitchen.domain.entities import (
    KitchenStation,
    OrderItemStation,
    ProductStation,
    StationSuggestion,
    StationTask,
    SuggestedStation,
    SuggestedTask,
    UnassignedIngredient,
    UnroutableProduct,
)
from restaurante.modules.kitchen.infrastructure.models import (
    KitchenStationModel,
    OrderItemStationModel,
    ProductStationModel,
)
from restaurante.modules.menu.infrastructure.models import (
    CategoryModel,
    ProductModel,
    ProductVariantModel,
)
from restaurante.modules.orders.infrastructure.models import OrderItemModel, OrderModel
from restaurante.modules.recipes.infrastructure.models import (
    IngredientModel,
    RecipeItemModel,
)
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel

_CANCELLED = "cancelled"


def _station(m: KitchenStationModel) -> KitchenStation:
    return KitchenStation(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        name=m.name,
        position=m.position,
        is_active=m.is_active,
    )


def read_tasks(raw: Any) -> list[StationTask]:
    """Único punto donde se entiende la forma guardada de `product_stations.tasks`.

    Convivió una forma vieja —una lista de cadenas— con la actual, que es una lista de objetos
    `{label, ingredient_id}`. Una cadena se lee como etiqueta sin insumo: exactamente lo que era.
    Así no hay backfill ni ventana en la que una asignación existente deje de enrutar, y ni el
    caso de uso ni la API llegan a ver la diferencia.

    Tolerante hasta el final: una entrada que no se entiende se descarta en vez de reventar el
    ruteo, porque un renglón perdido es un inconveniente y una excepción aquí es una comanda que
    no sale.
    """
    tasks: list[StationTask] = []
    for entry in raw or []:
        if isinstance(entry, str):
            tasks.append(StationTask(label=entry))
        elif isinstance(entry, dict):
            label = entry.get("label")
            if not isinstance(label, str):
                continue
            ingredient = entry.get("ingredient_id")
            tasks.append(
                StationTask(
                    label=label,
                    ingredient_id=(
                        uuid.UUID(ingredient) if isinstance(ingredient, str) else None
                    ),
                )
            )
    return tasks


def write_tasks(tasks: list[StationTask]) -> list[dict[str, str | None]]:
    """La forma que se persiste. `ingredient_id` viaja como texto: la columna es JSON."""
    return [
        {
            "label": t.label,
            "ingredient_id": str(t.ingredient_id) if t.ingredient_id else None,
        }
        for t in tasks
    ]


def _product_station(m: ProductStationModel) -> ProductStation:
    return ProductStation(
        id=m.id,
        tenant_id=m.tenant_id,
        product_id=m.product_id,
        kitchen_station_id=m.kitchen_station_id,
        role=m.role,
        tasks=read_tasks(m.tasks),
    )


def _ticket(m: OrderItemStationModel, *, notes: str | None = None) -> OrderItemStation:
    return OrderItemStation(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_item_id=m.order_item_id,
        kitchen_station_id=m.kitchen_station_id,
        status=m.status,
        role=m.role,
        tasks=list(m.tasks or []),
        ready_at=m.ready_at,
        entered_at=m.entered_at,
        notes=notes,
    )


class SqlAlchemyKitchenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def product_exists(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> bool:
        stmt = select(ProductModel.id).where(
            ProductModel.id == product_id, ProductModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def station_exists(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool:
        stmt = select(KitchenStationModel.id).where(
            KitchenStationModel.id == station_id,
            KitchenStationModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def order_exists(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> bool:
        stmt = select(OrderModel.id).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Stations ----------------------------------------------------------
    async def create_station(self, station: KitchenStation) -> KitchenStation:
        model = KitchenStationModel(
            tenant_id=station.tenant_id,
            branch_id=station.branch_id,
            name=station.name,
            position=station.position,
            is_active=station.is_active,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _station(model)

    async def _get_station_model(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> KitchenStationModel | None:
        stmt = select(KitchenStationModel).where(
            KitchenStationModel.id == station_id,
            KitchenStationModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID
    ) -> KitchenStation | None:
        model = await self._get_station_model(tenant_id, station_id)
        return _station(model) if model else None

    async def list_stations(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[KitchenStation]:
        stmt = (
            select(KitchenStationModel)
            .where(
                KitchenStationModel.tenant_id == tenant_id,
                KitchenStationModel.branch_id == branch_id,
            )
            .order_by(KitchenStationModel.position, KitchenStationModel.name)
        )
        return [_station(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_station(
        self, tenant_id: uuid.UUID, station_id: uuid.UUID, fields: dict[str, Any]
    ) -> KitchenStation | None:
        model = await self._get_station_model(tenant_id, station_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _station(model)

    # --- Product ↔ station -------------------------------------------------
    async def create_product_station(
        self, mapping: ProductStation
    ) -> ProductStation:
        model = ProductStationModel(
            tenant_id=mapping.tenant_id,
            product_id=mapping.product_id,
            kitchen_station_id=mapping.kitchen_station_id,
            role=mapping.role,
            tasks=write_tasks(mapping.tasks),
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "El producto ya está asignado a esa estación."
            ) from exc
        await self._session.refresh(model)
        return _product_station(model)

    async def product_station_exists(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool:
        stmt = select(ProductStationModel.id).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.product_id == product_id,
            ProductStationModel.kitchen_station_id == station_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def list_product_stations(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[ProductStation]:
        stmt = select(ProductStationModel).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.product_id == product_id,
        )
        return [
            _product_station(m) for m in (await self._session.execute(stmt)).scalars()
        ]

    async def variant_amounts(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> dict[uuid.UUID, str]:
        """Cuánto lleva ESTA variante de cada insumo, ya formateado para el pase.

        Una sola consulta por ítem de la orden, que `route_order` reutiliza para todas las
        estaciones de ese ítem: es el camino crítico de la comanda y no admite un round-trip por
        ticket.

        Un insumo ausente del diccionario significa que la variante no lo lleva — y eso es
        distinto de llevarlo sin cantidad conocida.
        """
        stmt = (
            select(
                RecipeItemModel.ingredient_id,
                RecipeItemModel.quantity,
                UnitOfMeasureModel.abbreviation,
                UnitOfMeasureModel.id,
            )
            .join(
                UnitOfMeasureModel,
                UnitOfMeasureModel.id == RecipeItemModel.unit_of_measure_id,
            )
            .where(
                RecipeItemModel.tenant_id == tenant_id,
                RecipeItemModel.product_variant_id == variant_id,
            )
        )
        rows = (await self._session.execute(stmt)).all()
        sub_units = await self._sub_units({row[3] for row in rows})
        return {
            ingredient_id: format_amount(quantity, unit_abbr, sub_units.get(unit_id))
            for ingredient_id, quantity, unit_abbr, unit_id in rows
        }

    async def _sub_units(
        self, unit_ids: set[uuid.UUID]
    ) -> dict[uuid.UUID, SubUnit]:
        """Por cada unidad, la menor de su familia: para `kg` devuelve `g`.

        Sale de `base_unit_id`/`conversion_factor`, que la tabla ya modela — quemar `kg→g` en el
        código lo duplicaría y se rompería con la primera unidad que alguien añada. Con varias
        candidatas gana la de menor factor, que es la más fina.
        """
        if not unit_ids:
            return {}
        stmt = select(
            UnitOfMeasureModel.base_unit_id,
            UnitOfMeasureModel.abbreviation,
            UnitOfMeasureModel.conversion_factor,
        ).where(
            UnitOfMeasureModel.base_unit_id.in_(unit_ids),
            UnitOfMeasureModel.conversion_factor.is_not(None),
        )
        finest: dict[uuid.UUID, SubUnit] = {}
        for base_id, abbreviation, factor in (
            await self._session.execute(stmt)
        ).all():
            current = finest.get(base_id)
            if current is None or factor < current.conversion_factor:
                finest[base_id] = SubUnit(
                    abbreviation=abbreviation, conversion_factor=factor
                )
        return finest

    async def suggest_product_stations(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, product_id: uuid.UUID
    ) -> StationSuggestion | None:
        """Qué estaciones implica la receta del producto y qué le debería cada una.

        Lectura cruzada a recetas por el repositorio, como `variant_has_recipe` la hace al revés,
        en vez de acoplar el servicio de cocina al de recetas. Devuelve ``None`` cuando el
        producto no existe en el tenant, para que la capa de aplicación responda 404.

        UNIÓN entre variantes a propósito (design §5): la receta es por variante y la estación por
        producto, así que si la variante grande mete un insumo de otra estación, esa estación hace
        falta de verdad. Los insumos se deduplican por id, de modo que uno compartido por dos
        variantes produce una sola tarea y aporta las dos variantes a `from_variants`.

        No escribe nada. Ni una fila de `product_stations` se toca aquí.
        """
        product = (
            await self._session.execute(
                select(ProductModel.id).where(
                    ProductModel.id == product_id,
                    ProductModel.tenant_id == tenant_id,
                )
            )
        ).scalar_one_or_none()
        if product is None:
            return None

        stmt = (
            select(
                IngredientModel.id,
                IngredientModel.name,
                func.coalesce(
                    RecipeItemModel.station_id, IngredientModel.default_station_id
                ),
                KitchenStationModel.name,
                KitchenStationModel.branch_id,
                ProductVariantModel.name,
                RecipeItemModel.quantity,
                UnitOfMeasureModel.abbreviation,
                UnitOfMeasureModel.id,
            )
            .select_from(ProductVariantModel)
            .join(
                RecipeItemModel,
                RecipeItemModel.product_variant_id == ProductVariantModel.id,
            )
            .join(IngredientModel, IngredientModel.id == RecipeItemModel.ingredient_id)
            .join(
                UnitOfMeasureModel,
                UnitOfMeasureModel.id == RecipeItemModel.unit_of_measure_id,
            )
            # La estación EFECTIVA: la que fija la línea de receta gana sobre el default del
            # insumo. "¿Dónde va el arroz?" sólo tiene respuesta por plato.
            .outerjoin(
                KitchenStationModel,
                KitchenStationModel.id
                == func.coalesce(
                    RecipeItemModel.station_id, IngredientModel.default_station_id
                ),
            )
            .where(
                ProductVariantModel.product_id == product_id,
                ProductVariantModel.tenant_id == tenant_id,
            )
            .order_by(KitchenStationModel.name, IngredientModel.name)
        )
        rows = (await self._session.execute(stmt)).all()
        sub_units = await self._sub_units({row[8] for row in rows})

        # station_id -> (station name, ingredient id -> task parts, variants)
        # La tarea se arma al final porque la cantidad puede venir de varias variantes y sólo
        # se sabe si es una sola cuando ya se leyeron todas.
        grouped: dict[
            uuid.UUID, tuple[str, dict[uuid.UUID, tuple[str, list[str]]], list[str]]
        ] = {}
        unassigned: dict[uuid.UUID, UnassignedIngredient] = {}
        for (
            ing_id,
            ing_name,
            station_id,
            station_name,
            station_branch,
            variant,
            quantity,
            unit_abbr,
            unit_id,
        ) in rows:
            in_other_branch = station_id is not None and station_branch != branch_id
            if station_id is None or in_other_branch:
                # Reported, never dropped: an ingredient that vanishes quietly is how a
                # product ends up with nobody cooking it.
                unassigned.setdefault(
                    ing_id,
                    UnassignedIngredient(
                        ingredient_id=ing_id,
                        name=ing_name,
                        default_station_in_other_branch=in_other_branch,
                    ),
                )
                continue
            _name, by_ingredient, variants = grouped.setdefault(
                station_id, (station_name, {}, [])
            )
            _ing_name, amounts = by_ingredient.setdefault(ing_id, (ing_name, []))
            amount = format_amount(quantity, unit_abbr, sub_units.get(unit_id))
            if amount not in amounts:
                amounts.append(amount)
            if variant is not None and variant not in variants:
                variants.append(variant)

        saved = {
            m.kitchen_station_id: [t.label for t in read_tasks(m.tasks)]
            for m in (
                await self._session.execute(
                    select(ProductStationModel).where(
                        ProductStationModel.tenant_id == tenant_id,
                        ProductStationModel.product_id == product_id,
                    )
                )
            ).scalars()
        }

        stations: list[SuggestedStation] = []
        for station_id, (name, by_ingredient, variants) in grouped.items():
            # La etiqueta NO lleva la cantidad: depende de la variante que se pida y eso sólo
            # se sabe al enrutar. `amounts` viaja aparte, para que el panel muestre lo que va a
            # producir.
            tasks = [
                SuggestedTask(label=ing_name, ingredient_id=ing_id, amounts=amounts)
                for ing_id, (ing_name, amounts) in by_ingredient.items()
            ]
            # Only a station that already HAS a saved mapping can have drifted. A station
            # merely suggested for the first time is new, not out of sync, and must not
            # light up the panel's drift notice.
            saved_tasks = saved.get(station_id)
            labels = [t.label for t in tasks]
            missing = (
                [] if saved_tasks is None else [t for t in labels if t not in saved_tasks]
            )
            stale = (
                [] if saved_tasks is None else [t for t in saved_tasks if t not in labels]
            )
            stations.append(
                SuggestedStation(
                    station_id=station_id,
                    station_name=name,
                    tasks=tasks,
                    from_variants=variants,
                    missing_from_saved=missing,
                    saved_no_longer_implied=stale,
                )
            )
        stations.sort(key=lambda s: s.station_name)
        return StationSuggestion(
            stations=stations,
            unassigned_ingredients=sorted(unassigned.values(), key=lambda i: i.name),
        )

    async def list_unroutable_products(
        self, tenant_id: uuid.UUID
    ) -> list[UnroutableProduct]:
        """Los productos que ninguna estación prepara, con cuántas variantes activas tienen.

        El conteo de variantes activas es lo que separa lo urgente de lo pendiente: sin ellas es
        una ficha a medio crear; con ellas es algo que se está vendiendo AHORA y que la cocina no
        va a ver. Por eso se devuelven los dos casos y se ordenan poniendo delante los que venden.
        """
        active_variants = (
            select(func.count(ProductVariantModel.id))
            .where(
                ProductVariantModel.product_id == ProductModel.id,
                ProductVariantModel.is_active.is_(True),
            )
            .correlate(ProductModel)
            .scalar_subquery()
        )
        mapped = (
            select(ProductStationModel.id)
            .where(ProductStationModel.product_id == ProductModel.id)
            .correlate(ProductModel)
            .exists()
        )
        stmt = (
            select(
                ProductModel.id,
                ProductModel.name,
                CategoryModel.name,
                active_variants.label("active_variants"),
            )
            .select_from(ProductModel)
            .outerjoin(CategoryModel, CategoryModel.id == ProductModel.category_id)
            .where(ProductModel.tenant_id == tenant_id, ~mapped)
            .order_by(active_variants.desc(), ProductModel.name)
        )
        return [
            UnroutableProduct(
                product_id=row[0],
                name=row[1],
                category_name=row[2],
                active_variants=int(row[3] or 0),
            )
            for row in (await self._session.execute(stmt)).all()
        ]

    async def list_stations_for_product(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, str | None, list[StationTask]]]:
        stmt = select(
            ProductStationModel.kitchen_station_id,
            ProductStationModel.role,
            ProductStationModel.tasks,
        ).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.product_id == product_id,
        )
        return [
            (row[0], row[1], read_tasks(row[2]))
            for row in (await self._session.execute(stmt)).all()
        ]

    async def get_product_station(
        self, tenant_id: uuid.UUID, mapping_id: uuid.UUID
    ) -> ProductStation | None:
        stmt = select(ProductStationModel).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.id == mapping_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _product_station(model) if model else None

    async def update_product_station(
        self, tenant_id: uuid.UUID, mapping_id: uuid.UUID, fields: dict[str, Any]
    ) -> ProductStation | None:
        stmt = select(ProductStationModel).where(
            ProductStationModel.tenant_id == tenant_id,
            ProductStationModel.id == mapping_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        if model is None:
            return None
        for key, value in fields.items():
            # `tasks` es lo único que no se guarda como llega: la entidad es estructurada y la
            # columna es JSON, así que la serialización vive aquí y no en el caso de uso.
            setattr(model, key, write_tasks(value) if key == "tasks" else value)
        await self._session.commit()
        await self._session.refresh(model)
        return _product_station(model)

    async def delete_product_station(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, station_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(ProductStationModel).where(
                ProductStationModel.tenant_id == tenant_id,
                ProductStationModel.product_id == product_id,
                ProductStationModel.kitchen_station_id == station_id,
            )
        )
        await self._session.commit()

    # --- Routing support ---------------------------------------------------
    async def variant_product_id(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = select(ProductVariantModel.product_id).where(
            ProductVariantModel.id == variant_id,
            ProductVariantModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def product_name(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID
    ) -> str | None:
        """El nombre del producto, para poder NOMBRAR el que no llegó a la cocina."""
        stmt = select(ProductModel.name).where(
            ProductModel.id == product_id, ProductModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_non_cancelled_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
        stmt = select(
            OrderItemModel.id,
            OrderItemModel.product_variant_id,
            OrderItemModel.branch_id,
        ).where(
            OrderItemModel.tenant_id == tenant_id,
            OrderItemModel.order_id == order_id,
            OrderItemModel.status != _CANCELLED,
        )
        return [
            (row[0], row[1], row[2])
            for row in (await self._session.execute(stmt)).all()
        ]

    async def ticket_exists(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID, station_id: uuid.UUID
    ) -> bool:
        stmt = select(OrderItemStationModel.id).where(
            OrderItemStationModel.tenant_id == tenant_id,
            OrderItemStationModel.order_item_id == order_item_id,
            OrderItemStationModel.kitchen_station_id == station_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def create_ticket(self, ticket: OrderItemStation) -> OrderItemStation:
        model = OrderItemStationModel(
            tenant_id=ticket.tenant_id,
            branch_id=ticket.branch_id,
            order_item_id=ticket.order_item_id,
            kitchen_station_id=ticket.kitchen_station_id,
            status=ticket.status,
            role=ticket.role,
            tasks=ticket.tasks,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            # The (order_item, station) unique constraint fired: a concurrent route already
            # created this ticket. Surface it as a conflict so the caller can skip it.
            await self._session.rollback()
            raise ConflictError("El ítem ya está ruteado a esa estación.") from exc
        await self._session.refresh(model)
        return _ticket(model)

    # --- Ready rollup support ----------------------------------------------
    async def order_id_for_item(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> uuid.UUID | None:
        stmt = select(OrderItemModel.order_id).where(
            OrderItemModel.id == order_item_id,
            OrderItemModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def list_order_ticket_statuses(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[str]:
        stmt = (
            select(OrderItemStationModel.status)
            .join(
                OrderItemModel,
                OrderItemModel.id == OrderItemStationModel.order_item_id,
            )
            .where(
                OrderItemStationModel.tenant_id == tenant_id,
                OrderItemModel.order_id == order_id,
            )
        )
        return list((await self._session.execute(stmt)).scalars())

    # --- KDS board ---------------------------------------------------------
    async def list_tickets(
        self,
        tenant_id: uuid.UUID,
        station_id: uuid.UUID,
        *,
        status: str | None = None,
        open_session_only: bool = False,
    ) -> list[OrderItemStation]:
        stmt = (
            select(OrderItemStationModel, OrderItemModel.notes)
            .join(
                OrderItemModel, OrderItemModel.id == OrderItemStationModel.order_item_id
            )
            .where(
                OrderItemStationModel.tenant_id == tenant_id,
                OrderItemStationModel.kitchen_station_id == station_id,
            )
        )
        if open_session_only:
            # Live board scope: only tickets whose order belongs to the branch's OPEN cash
            # session. The joins drop null-session tickets and match nothing with no open session.
            stmt = stmt.join(
                OrderModel, OrderItemModel.order_id == OrderModel.id
            ).join(
                CashSessionModel, OrderModel.cash_session_id == CashSessionModel.id
            ).where(CashSessionModel.status == "open")
        if status is not None:
            stmt = stmt.where(OrderItemStationModel.status == status)
        stmt = stmt.order_by(OrderItemStationModel.entered_at)
        rows = (await self._session.execute(stmt)).all()
        return [_ticket(m, notes=notes) for (m, notes) in rows]

    async def _get_ticket_model(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> OrderItemStationModel | None:
        stmt = select(OrderItemStationModel).where(
            OrderItemStationModel.id == ticket_id,
            OrderItemStationModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID
    ) -> OrderItemStation | None:
        model = await self._get_ticket_model(tenant_id, ticket_id)
        return _ticket(model) if model else None

    async def update_ticket(
        self, tenant_id: uuid.UUID, ticket_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderItemStation | None:
        model = await self._get_ticket_model(tenant_id, ticket_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _ticket(model)
