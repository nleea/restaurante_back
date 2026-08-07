"""Persistence adapter for the Orders module over SQLAlchemy async.

Each write method commits its own unit of work and filters explicitly by
``tenant_id`` (and ``branch_id`` where applicable). Money fields are derived
server-side: ``recompute_item`` sets a line's subtotal from its unit price,
quantity and addons; ``recompute_totals`` sets the order subtotal/total from its
non-cancelled items and discount.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import delete as sql_delete
from sqlalchemy import exists, func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from restaurante.modules.cash.domain.entities import CashSession
from restaurante.modules.cash.infrastructure.models import (
    CashMovementModel,
    CashSessionModel,
)
from restaurante.modules.customers.infrastructure.models import (
    CustomerCreditModel,
    CustomerModel,
)
from restaurante.modules.inventory.infrastructure.models import (
    InventoryMovementModel,
    InventoryStockModel,
)
from restaurante.modules.kitchen.infrastructure.models import (
    OrderItemStationModel,
)
from restaurante.modules.menu.infrastructure.models import (
    AddonModel,
    ProductVariantModel,
)
from restaurante.modules.orders.domain.entities import (
    CLAIM_PENDING,
    Cancellation,
    DiningTable,
    Order,
    OrderItem,
    OrderItemAddon,
    OrderPayment,
    OrderPaymentClaim,
    OrderRefund,
    ReceiptPrint,
    TableBill,
)
from restaurante.modules.orders.domain.table_code import mint_table_code
from restaurante.modules.orders.infrastructure.models import (
    CancellationModel,
    DiningTableModel,
    OrderItemAddonModel,
    OrderItemModel,
    OrderModel,
    OrderPaymentClaimModel,
    OrderPaymentModel,
    OrderRefundModel,
    ReceiptPrintModel,
    TableBillModel,
)
from restaurante.modules.recipes.infrastructure.models import RecipeItemModel
from restaurante.modules.staff.infrastructure.models import EmployeeModel
from restaurante.shared.domain.errors import ConflictError
from restaurante.shared.tenancy.models import BranchModel, TenantModel

_CANCELLED = "cancelled"
_OPEN = "open"
_BILL_SETTLED = "settled"


def _table(m: DiningTableModel) -> DiningTable:
    return DiningTable(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        number=m.number,
        code=m.code,
        capacity=m.capacity,
        status=m.status,
        is_active=m.is_active,
    )


def _bill(m: TableBillModel) -> TableBill:
    return TableBill(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        dining_table_id=m.dining_table_id,
        opened_by_employee_id=m.opened_by_employee_id,
        status=m.status,
        total=m.total,
        closed_at=m.closed_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _order(m: OrderModel) -> Order:
    return Order(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        channel=m.channel,
        employee_id=m.employee_id,
        status=m.status,
        subtotal=m.subtotal,
        discount=m.discount,
        delivery_fee=m.delivery_fee,
        total=m.total,
        kitchen_state=m.kitchen_state,
        payment_method=m.payment_method,
        diner_name=m.diner_name,
        origin=m.origin,
        dining_table_id=m.dining_table_id,
        customer_id=m.customer_id,
        table_bill_id=m.table_bill_id,
        whatsapp_contact_id=m.whatsapp_contact_id,
        cash_session_id=m.cash_session_id,
        closed_at=m.closed_at,
        edit_token=m.edit_token,
        edit_token_expires_at=m.edit_token_expires_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _item(m: OrderItemModel, *, sent: bool = False) -> OrderItem:
    return OrderItem(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        product_variant_id=m.product_variant_id,
        unit_price=m.unit_price,
        line_subtotal=m.line_subtotal,
        quantity=m.quantity,
        status=m.status,
        notes=m.notes,
        sent=sent,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _item_addon(m: OrderItemAddonModel) -> OrderItemAddon:
    return OrderItemAddon(
        id=m.id,
        tenant_id=m.tenant_id,
        order_item_id=m.order_item_id,
        addon_id=m.addon_id,
        applied_price=m.applied_price,
    )


def _cancellation(m: CancellationModel) -> Cancellation:
    return Cancellation(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        reason=m.reason,
        requires_authorization=m.requires_authorization,
        requested_by_employee_id=m.requested_by_employee_id,
        status=m.status,
        order_item_id=m.order_item_id,
        authorized_by_employee_id=m.authorized_by_employee_id,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _refund(m: OrderRefundModel) -> OrderRefund:
    return OrderRefund(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        amount=m.amount,
        method=m.method,
        status=m.status,
        resolved_by_employee_id=m.resolved_by_employee_id,
        resolved_at=m.resolved_at,
        reason=m.reason,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def _payment(m: OrderPaymentModel) -> OrderPayment:
    return OrderPayment(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        cash_session_id=m.cash_session_id,
        amount=m.amount,
        method=m.method,
        employee_id=m.employee_id,
        diner_reference=m.diner_reference,
        created_at=m.created_at,
    )


def _payment_claim(m: OrderPaymentClaimModel) -> OrderPaymentClaim:
    return OrderPaymentClaim(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        amount=m.amount,
        method=m.method,
        proof_url=m.proof_url,
        status=m.status,
        rejection_reason=m.rejection_reason,
        resolved_by_employee_id=m.resolved_by_employee_id,
        resolved_at=m.resolved_at,
        created_at=m.created_at,
    )


def _cash_session(m: CashSessionModel) -> CashSession:
    return CashSession(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        opened_by_employee_id=m.opened_by_employee_id,
        opening_amount=m.opening_amount,
        status=m.status,
        opened_at=m.opened_at,
        closed_by_employee_id=m.closed_by_employee_id,
        counted_amount=m.counted_amount,
        expected_amount=m.expected_amount,
        difference=m.difference,
        closed_at=m.closed_at,
    )


def _receipt(m: ReceiptPrintModel) -> ReceiptPrint:
    return ReceiptPrint(
        id=m.id,
        tenant_id=m.tenant_id,
        branch_id=m.branch_id,
        order_id=m.order_id,
        table_bill_id=m.table_bill_id,
        employee_id=m.employee_id,
        is_reprint=m.is_reprint,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


class SqlAlchemyOrdersRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        # Cada método de escritura cierra su propia unidad de trabajo, que es lo correcto para
        # un gesto suelto. Cobrar la cuenta de una mesa NO es un gesto suelto: son N pagos, N
        # movimientos de caja, N descuentos de inventario y N cierres, y dejar la mitad hechos
        # es el peor resultado posible de esta capacidad —una comanda cerrada y otra cobrada
        # sin cerrar—. `unit_of_work()` aplaza esos commits para que sean uno solo.
        self._defer_commit = False

    @asynccontextmanager
    async def unit_of_work(self) -> AsyncIterator[None]:
        """Agrupa varias escrituras en UNA transacción: o quedan todas, o no queda ninguna.

        Se implementa aplazando el commit de los métodos que ya existen en vez de duplicar lo
        que hacen. La alternativa —un método aparte que reescriba pagos, movimientos y cierres—
        pondría la lógica del dinero en dos sitios, y dos copias de eso se desincronizan.

        No es reentrante a propósito: anidar unidades de trabajo sugiere que alguien no sabe
        quién cierra la transacción, y en código de dinero esa duda hay que resolverla arriba.
        """
        if self._defer_commit:
            raise RuntimeError("Ya hay una unidad de trabajo abierta en este repositorio.")
        self._defer_commit = True
        try:
            yield
        except BaseException:
            await self._session.rollback()
            raise
        else:
            await self._session.commit()
        finally:
            self._defer_commit = False

    async def _commit(self) -> None:
        """Cierra la unidad de trabajo, o la empuja si quien manda cierra al final.

        Dentro de una unidad de trabajo NO se commitea, pero sí se hace `flush`: las filas
        tienen que llegar a la base —dentro de la transacción abierta— para que lo que venga
        después las vea. Sin el flush, un `refresh()` posterior falla ("not persistent") y las
        consultas del propio cobro no verían los pagos que acaba de escribir.
        """
        if self._defer_commit:
            await self._session.flush()
        else:
            await self._session.commit()

    # --- Reference existence checks ----------------------------------------
    async def branch_exists(self, tenant_id: uuid.UUID, branch_id: uuid.UUID) -> bool:
        stmt = select(BranchModel.id).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def employee_exists(
        self, tenant_id: uuid.UUID, employee_id: uuid.UUID
    ) -> bool:
        stmt = select(EmployeeModel.id).where(
            EmployeeModel.id == employee_id, EmployeeModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def customer_exists(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID
    ) -> bool:
        stmt = select(CustomerModel.id).where(
            CustomerModel.id == customer_id, CustomerModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def variant_exists(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool:
        stmt = select(ProductVariantModel.id).where(
            ProductVariantModel.id == product_variant_id,
            ProductVariantModel.tenant_id == tenant_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    async def variant_has_recipe(
        self, tenant_id: uuid.UUID, product_variant_id: uuid.UUID
    ) -> bool:
        """True when the variant has ≥1 recipe item (reads the recipes table).

        Follows the same cross-module read as `consume_inventory_for_order`; the
        sale boundary is the load-bearing gate for the recipe invariant.
        """
        stmt = select(
            exists().where(
                RecipeItemModel.tenant_id == tenant_id,
                RecipeItemModel.product_variant_id == product_variant_id,
            )
        )
        return bool((await self._session.execute(stmt)).scalar())

    async def addon_exists(self, tenant_id: uuid.UUID, addon_id: uuid.UUID) -> bool:
        stmt = select(AddonModel.id).where(
            AddonModel.id == addon_id, AddonModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Dining tables -----------------------------------------------------
    async def _branch_table_codes(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> set[str]:
        stmt = select(DiningTableModel.code).where(
            DiningTableModel.tenant_id == tenant_id,
            DiningTableModel.branch_id == branch_id,
        )
        return {c for c in (await self._session.execute(stmt)).scalars()}

    async def create_dining_table(self, table: DiningTable) -> DiningTable:
        # El código se acuña AQUÍ y nunca lo trae el llamante: es del papel pegado a la mesa, no
        # de quien crea la mesa. `taken` es por sede porque la unicidad es por sede —la sede va
        # en la ruta del QR—, y de todas formas quien garantiza la unicidad de verdad es el
        # índice `(branch_id, code)`: dos peticiones concurrentes leen el mismo `taken`.
        model = DiningTableModel(
            tenant_id=table.tenant_id,
            branch_id=table.branch_id,
            number=table.number,
            code=mint_table_code(
                await self._branch_table_codes(table.tenant_id, table.branch_id)
            ),
            capacity=table.capacity,
            status=table.status,
            is_active=table.is_active,
        )
        self._session.add(model)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise ConflictError(
                "Ya existe una mesa con ese número en la sucursal."
            ) from exc
        await self._session.refresh(model)
        return _table(model)

    async def _get_table_model(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID
    ) -> DiningTableModel | None:
        stmt = select(DiningTableModel).where(
            DiningTableModel.id == table_id, DiningTableModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_dining_table(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID
    ) -> DiningTable | None:
        model = await self._get_table_model(tenant_id, table_id)
        return _table(model) if model else None

    async def list_dining_tables(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> list[DiningTable]:
        stmt = (
            select(DiningTableModel)
            .where(
                DiningTableModel.tenant_id == tenant_id,
                DiningTableModel.branch_id == branch_id,
            )
            .order_by(DiningTableModel.number)
        )
        return [_table(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_dining_table(
        self, tenant_id: uuid.UUID, table_id: uuid.UUID, fields: dict[str, Any]
    ) -> DiningTable | None:
        model = await self._get_table_model(tenant_id, table_id)
        if model is None:
            return None
        # `code` es inmutable y se descarta aquí, no en la API: es una propiedad de la mesa, no
        # una regla de un endpoint. Renumerar el salón ("ahora la 5 es la 12") no puede invalidar
        # una calcomanía ya pegada, y ése es exactamente el camino por el que pasaría.
        for key, value in fields.items():
            if key == "code":
                continue
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _table(model)

    async def tenant_slug(self, tenant_id: uuid.UUID) -> str | None:
        # `skip_tenant_filter`: `tenants` no es una tabla con `tenant_id` — es la tabla DE los
        # tenants, y el filtro automático la dejaría sin filas.
        stmt = select(TenantModel.slug).where(TenantModel.id == tenant_id)
        return (
            await self._session.execute(stmt.execution_options(skip_tenant_filter=True))
        ).scalar_one_or_none()

    async def branch_code(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> str | None:
        stmt = select(BranchModel.code).where(
            BranchModel.id == branch_id, BranchModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def count_open_orders_on_table(
        self,
        tenant_id: uuid.UUID,
        table_id: uuid.UUID,
        exclude_order_id: uuid.UUID | None = None,
    ) -> int:
        stmt = select(func.count()).where(
            OrderModel.tenant_id == tenant_id,
            OrderModel.dining_table_id == table_id,
            OrderModel.status == _OPEN,
        )
        if exclude_order_id is not None:
            stmt = stmt.where(OrderModel.id != exclude_order_id)
        return int((await self._session.execute(stmt)).scalar_one())

    # --- Table bills -------------------------------------------------------
    async def create_table_bill(self, bill: TableBill) -> TableBill:
        model = TableBillModel(
            tenant_id=bill.tenant_id,
            branch_id=bill.branch_id,
            dining_table_id=bill.dining_table_id,
            opened_by_employee_id=bill.opened_by_employee_id,
            status=bill.status,
        )
        self._session.add(model)
        await self._session.flush()
        return _bill(model)

    async def get_table_bill(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID
    ) -> TableBill | None:
        stmt = select(TableBillModel).where(
            TableBillModel.id == bill_id, TableBillModel.tenant_id == tenant_id
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _bill(model) if model else None

    async def claim_orders_for_bill(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID, order_ids: list[uuid.UUID]
    ) -> int:
        """Reclama esas comandas para la cuenta. Devuelve cuántas se llevó de verdad.

        `WHERE table_bill_id IS NULL` es la pieza que hace esto seguro entre cajeros: dos
        peticiones que intenten agrupar la misma comanda no pueden ganar las dos, porque la
        segunda no encuentra la fila que buscaba. Comparar el recuento con lo pedido es lo que
        convierte la carrera en un error legible en vez de en una cuenta a la que le falta
        gente sin decirlo.

        Comprobar antes y escribir después NO valdría: entre la lectura y la escritura cabe
        el otro cajero.
        """
        result = await self._session.execute(
            update(OrderModel)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.id.in_(order_ids),
                OrderModel.status == _OPEN,
                OrderModel.table_bill_id.is_(None),
            )
            .values(table_bill_id=bill_id)
        )
        return cast(CursorResult[Any], result).rowcount

    async def list_bill_members(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID
    ) -> list[Order]:
        """Los miembros en ORDEN DETERMINISTA: `created_at`, y `id` para desempatar.

        El orden no es cosmético — es el que sigue el reparto en cascada, así que dos cobros
        idénticos tienen que producir las mismas asignaciones.
        """
        stmt = (
            select(OrderModel)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.table_bill_id == bill_id,
            )
            .order_by(OrderModel.created_at.asc(), OrderModel.id.asc())
        )
        return [_order(m) for m in (await self._session.execute(stmt)).scalars()]

    async def release_bill_orders(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            update(OrderModel)
            .where(
                OrderModel.tenant_id == tenant_id,
                OrderModel.table_bill_id == bill_id,
            )
            .values(table_bill_id=None)
        )

    async def delete_table_bill(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID
    ) -> None:
        """Disolver BORRA la cuenta en vez de dejarla en un tercer estado.

        No llegó a existir como hecho: no movió dinero y no cerró nada. Un estado `dissolved`
        sería ruido que habría que filtrar en cada consulta para siempre.
        """
        await self._session.execute(
            sql_delete(TableBillModel).where(
                TableBillModel.id == bill_id, TableBillModel.tenant_id == tenant_id
            )
        )

    async def settle_table_bill(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID, total: Decimal
    ) -> None:
        await self._session.execute(
            update(TableBillModel)
            .where(
                TableBillModel.id == bill_id, TableBillModel.tenant_id == tenant_id
            )
            .values(status=_BILL_SETTLED, total=total, closed_at=datetime.now(UTC))
        )

    async def bill_receipt_data(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID
    ) -> dict[str, Any] | None:
        """Todo lo que la tirilla necesita, en una consulta por pieza.

        Se lee aquí y no se compone en el navegador porque un papel que se entrega al cliente
        no puede depender de que el front acierte a juntar seis llamadas: si una falla, sale
        una tirilla incompleta y nadie se entera hasta que alguien la mira.
        """
        bill = await self.get_table_bill(tenant_id, bill_id)
        if bill is None:
            return None

        tenant = (
            await self._session.execute(
                select(
                    TenantModel.name, TenantModel.tax_id, TenantModel.address
                )
                .where(TenantModel.id == tenant_id)
                .execution_options(skip_tenant_filter=True)
            )
        ).first()
        branch = (
            await self._session.execute(
                select(BranchModel.name, BranchModel.address).where(
                    BranchModel.id == bill.branch_id
                )
            )
        ).first()
        table_number = (
            await self._session.execute(
                select(DiningTableModel.number).where(
                    DiningTableModel.id == bill.dining_table_id
                )
            )
        ).scalar_one_or_none()

        members = await self.list_bill_members(tenant_id, bill_id)
        member_rows: list[dict[str, Any]] = []
        methods: set[str] = set()
        for member in members:
            assert member.id is not None
            lines = (
                await self._session.execute(
                    select(
                        OrderItemModel.quantity,
                        OrderItemModel.line_subtotal,
                        ProductVariantModel.name.label("variant_name"),
                    )
                    .join(
                        ProductVariantModel,
                        ProductVariantModel.id == OrderItemModel.product_variant_id,
                    )
                    .where(
                        OrderItemModel.order_id == member.id,
                        OrderItemModel.status != _CANCELLED,
                    )
                    .order_by(OrderItemModel.created_at.asc())
                )
            ).all()
            for method in (
                await self._session.execute(
                    select(OrderPaymentModel.method).where(
                        OrderPaymentModel.order_id == member.id
                    )
                )
            ).scalars():
                methods.add(method)
            member_rows.append(
                {
                    "order_id": member.id,
                    "diner_name": member.diner_name,
                    "total": member.total,
                    "lines": [
                        {
                            "name": row.variant_name,
                            "quantity": row.quantity,
                            "line_subtotal": row.line_subtotal,
                        }
                        for row in lines
                    ],
                }
            )

        return {
            "bill": bill,
            "business_name": tenant.name if tenant else "",
            "tax_id": tenant.tax_id if tenant else None,
            "business_address": (branch.address if branch else None)
            or (tenant.address if tenant else None),
            "branch_name": branch.name if branch else "",
            "table_number": table_number or "",
            "members": member_rows,
            "methods": sorted(methods),
        }

    async def bill_has_receipt(
        self, tenant_id: uuid.UUID, bill_id: uuid.UUID
    ) -> bool:
        stmt = select(
            exists().where(
                ReceiptPrintModel.tenant_id == tenant_id,
                ReceiptPrintModel.table_bill_id == bill_id,
            )
        )
        return bool((await self._session.execute(stmt)).scalar())

    # --- Orders ------------------------------------------------------------
    async def create_order(self, order: Order) -> Order:
        model = OrderModel(
            tenant_id=order.tenant_id,
            branch_id=order.branch_id,
            channel=order.channel,
            employee_id=order.employee_id,
            status=order.status,
            diner_name=order.diner_name,
            origin=order.origin,
            payment_method=order.payment_method,
            subtotal=order.subtotal,
            discount=order.discount,
            delivery_fee=order.delivery_fee,
            total=order.total,
            dining_table_id=order.dining_table_id,
            customer_id=order.customer_id,
            whatsapp_contact_id=order.whatsapp_contact_id,
            cash_session_id=order.cash_session_id,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    async def _get_order_model(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderModel | None:
        stmt = select(OrderModel).where(
            OrderModel.id == order_id, OrderModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def set_edit_token(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        token: str,
        expires_at: datetime,
    ) -> None:
        await self._session.execute(
            update(OrderModel)
            .where(OrderModel.id == order_id, OrderModel.tenant_id == tenant_id)
            .values(edit_token=token, edit_token_expires_at=expires_at)
        )
        await self._session.commit()

    async def get_order_by_edit_token(self, token: str) -> Order | None:
        if not token:
            return None
        model = (
            await self._session.execute(
                select(OrderModel).where(OrderModel.edit_token == token)
            )
        ).scalar_one_or_none()
        return _order(model) if model else None

    async def get_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order | None:
        model = await self._get_order_model(tenant_id, order_id)
        return _order(model) if model else None

    async def list_orders(
        self,
        tenant_id: uuid.UUID,
        *,
        branch_id: uuid.UUID | None = None,
        status: str | None = None,
        dining_table_id: uuid.UUID | None = None,
        open_session_only: bool = False,
        whatsapp_contact_id: uuid.UUID | None = None,
    ) -> list[Order]:
        stmt = select(OrderModel).where(OrderModel.tenant_id == tenant_id)
        if branch_id is not None:
            stmt = stmt.where(OrderModel.branch_id == branch_id)
        if status is not None:
            stmt = stmt.where(OrderModel.status == status)
        if dining_table_id is not None:
            stmt = stmt.where(OrderModel.dining_table_id == dining_table_id)
        if whatsapp_contact_id is not None:
            stmt = stmt.where(OrderModel.whatsapp_contact_id == whatsapp_contact_id)
        if open_session_only:
            # Live salón scope: only orders of the branch's OPEN cash session. The join drops
            # null-session rows and, with no open session, matches nothing.
            stmt = stmt.join(
                CashSessionModel, OrderModel.cash_session_id == CashSessionModel.id
            ).where(CashSessionModel.status == "open")
        stmt = stmt.order_by(OrderModel.created_at.desc())
        return [_order(m) for m in (await self._session.execute(stmt)).scalars()]

    async def update_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, fields: dict[str, Any]
    ) -> Order | None:
        model = await self._get_order_model(tenant_id, order_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    async def close_order(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        status: str,
        closed_at: datetime,
        customer_id: uuid.UUID | None,
        total: Decimal,
    ) -> Order | None:
        """Flip the order to closed and, when a customer is linked, bump that customer's purchase
        stats atomically in the same commit. The increment is a SQL column expression (safe under
        concurrency); exactly-once is guaranteed by the caller's open-status guard."""
        model = await self._get_order_model(tenant_id, order_id)
        if model is None:
            return None
        model.status = status
        model.closed_at = closed_at
        if customer_id is not None:
            await self._session.execute(
                update(CustomerModel)
                .where(
                    CustomerModel.id == customer_id,
                    CustomerModel.tenant_id == tenant_id,
                )
                .values(
                    total_spent=CustomerModel.total_spent + total,
                    order_count=CustomerModel.order_count + 1,
                    last_purchase_at=closed_at,
                )
            )
        await self._commit()
        await self._session.refresh(model)
        return _order(model)

    async def recompute_totals(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Order:
        model = await self._get_order_model(tenant_id, order_id)
        if model is None:
            raise ConflictError(f"Orden no encontrada: {order_id}")
        subtotal_stmt = select(
            func.coalesce(func.sum(OrderItemModel.line_subtotal), 0)
        ).where(
            OrderItemModel.tenant_id == tenant_id,
            OrderItemModel.order_id == order_id,
            OrderItemModel.status != _CANCELLED,
        )
        subtotal = Decimal(
            str((await self._session.execute(subtotal_stmt)).scalar_one())
        )
        model.subtotal = subtotal
        model.total = subtotal - model.discount + model.delivery_fee
        await self._session.commit()
        await self._session.refresh(model)
        return _order(model)

    # --- Order items -------------------------------------------------------
    async def create_item(self, item: OrderItem) -> OrderItem:
        model = OrderItemModel(
            tenant_id=item.tenant_id,
            branch_id=item.branch_id,
            order_id=item.order_id,
            product_variant_id=item.product_variant_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            line_subtotal=item.line_subtotal,
            status=item.status,
            notes=item.notes,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _item(model)

    async def _get_item_model(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItemModel | None:
        stmt = select(OrderItemModel).where(
            OrderItemModel.id == item_id, OrderItemModel.tenant_id == tenant_id
        )
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def get_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItem | None:
        model = await self._get_item_model(tenant_id, item_id)
        return _item(model) if model else None

    async def list_items(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderItem]:
        stmt = (
            select(OrderItemModel)
            .where(
                OrderItemModel.tenant_id == tenant_id,
                OrderItemModel.order_id == order_id,
            )
            .order_by(OrderItemModel.created_at)
        )
        models = list((await self._session.execute(stmt)).scalars())
        # An item is "sent" (en cocina) once it has ≥1 kitchen ticket. One grouped query over
        # the order's item ids, not N+1.
        item_ids = [m.id for m in models]
        sent_ids: set[uuid.UUID] = set()
        if item_ids:
            sent_stmt = select(OrderItemStationModel.order_item_id).where(
                OrderItemStationModel.tenant_id == tenant_id,
                OrderItemStationModel.order_item_id.in_(item_ids),
            )
            sent_ids = {
                row for row in (await self._session.execute(sent_stmt)).scalars()
            }
        return [_item(m, sent=m.id in sent_ids) for m in models]

    async def update_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, fields: dict[str, Any]
    ) -> OrderItem | None:
        model = await self._get_item_model(tenant_id, item_id)
        if model is None:
            return None
        for key, value in fields.items():
            setattr(model, key, value)
        await self._session.commit()
        await self._session.refresh(model)
        return _item(model)

    async def _addons_sum(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> Decimal:
        stmt = select(
            func.coalesce(func.sum(OrderItemAddonModel.applied_price), 0)
        ).where(
            OrderItemAddonModel.tenant_id == tenant_id,
            OrderItemAddonModel.order_item_id == item_id,
        )
        return Decimal(str((await self._session.execute(stmt)).scalar_one()))

    async def recompute_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID
    ) -> OrderItem | None:
        model = await self._get_item_model(tenant_id, item_id)
        if model is None:
            return None
        addons = await self._addons_sum(tenant_id, item_id)
        model.line_subtotal = model.unit_price * model.quantity + addons
        await self._session.commit()
        await self._session.refresh(model)
        return _item(model)

    async def delete_item(self, tenant_id: uuid.UUID, item_id: uuid.UUID) -> None:
        await self._session.execute(
            sql_delete(OrderItemModel).where(
                OrderItemModel.tenant_id == tenant_id, OrderItemModel.id == item_id
            )
        )
        await self._session.commit()

    # --- Item addons -------------------------------------------------------
    async def create_item_addon(self, addon: OrderItemAddon) -> OrderItemAddon:
        model = OrderItemAddonModel(
            tenant_id=addon.tenant_id,
            order_item_id=addon.order_item_id,
            addon_id=addon.addon_id,
            applied_price=addon.applied_price,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _item_addon(model)

    async def get_item_addon(
        self, tenant_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> OrderItemAddon | None:
        stmt = select(OrderItemAddonModel).where(
            OrderItemAddonModel.id == item_addon_id,
            OrderItemAddonModel.tenant_id == tenant_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _item_addon(model) if model else None

    async def list_item_addons(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> list[OrderItemAddon]:
        stmt = select(OrderItemAddonModel).where(
            OrderItemAddonModel.tenant_id == tenant_id,
            OrderItemAddonModel.order_item_id == order_item_id,
        )
        return [_item_addon(m) for m in (await self._session.execute(stmt)).scalars()]

    async def delete_item_addon(
        self, tenant_id: uuid.UUID, item_addon_id: uuid.UUID
    ) -> None:
        await self._session.execute(
            sql_delete(OrderItemAddonModel).where(
                OrderItemAddonModel.tenant_id == tenant_id,
                OrderItemAddonModel.id == item_addon_id,
            )
        )
        await self._session.commit()

    # --- Cancellations / receipts -----------------------------------------
    async def create_cancellation(self, cancellation: Cancellation) -> Cancellation:
        model = CancellationModel(
            tenant_id=cancellation.tenant_id,
            branch_id=cancellation.branch_id,
            order_id=cancellation.order_id,
            order_item_id=cancellation.order_item_id,
            reason=cancellation.reason,
            requires_authorization=cancellation.requires_authorization,
            requested_by_employee_id=cancellation.requested_by_employee_id,
            authorized_by_employee_id=cancellation.authorized_by_employee_id,
            status=cancellation.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _cancellation(model)

    async def create_receipt_print(self, receipt: ReceiptPrint) -> ReceiptPrint:
        model = ReceiptPrintModel(
            tenant_id=receipt.tenant_id,
            branch_id=receipt.branch_id,
            order_id=receipt.order_id,
            table_bill_id=receipt.table_bill_id,
            employee_id=receipt.employee_id,
            is_reprint=receipt.is_reprint,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _receipt(model)

    async def order_has_receipt(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool:
        stmt = select(ReceiptPrintModel.id).where(
            ReceiptPrintModel.tenant_id == tenant_id,
            ReceiptPrintModel.order_id == order_id,
        )
        return (await self._session.execute(stmt)).scalar_one_or_none() is not None

    # --- Payments (orders ↔ cash integration) ------------------------------
    async def get_open_cash_session(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> CashSession | None:
        stmt = select(CashSessionModel).where(
            CashSessionModel.tenant_id == tenant_id,
            CashSessionModel.branch_id == branch_id,
            CashSessionModel.status == "open",
        )
        model = (await self._session.execute(stmt)).scalars().first()
        return _cash_session(model) if model else None

    async def register_payment(self, payment: OrderPayment) -> OrderPayment:
        """Persist the order payment and the matching `sale` cash movement atomically."""
        payment_model = OrderPaymentModel(
            tenant_id=payment.tenant_id,
            branch_id=payment.branch_id,
            order_id=payment.order_id,
            cash_session_id=payment.cash_session_id,
            amount=payment.amount,
            method=payment.method,
            diner_reference=payment.diner_reference,
            employee_id=payment.employee_id,
        )
        movement_model = CashMovementModel(
            tenant_id=payment.tenant_id,
            branch_id=payment.branch_id,
            cash_session_id=payment.cash_session_id,
            type="in",
            category="sale",
            concept="sale",
            amount=payment.amount,
            method=payment.method,
            reference_id=payment.order_id,
        )
        self._session.add(payment_model)
        self._session.add(movement_model)
        await self._commit()
        await self._session.refresh(payment_model)
        return _payment(payment_model)

    async def list_payments(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPayment]:
        stmt = (
            select(OrderPaymentModel)
            .where(
                OrderPaymentModel.tenant_id == tenant_id,
                OrderPaymentModel.order_id == order_id,
            )
            .order_by(OrderPaymentModel.created_at)
        )
        return [_payment(m) for m in (await self._session.execute(stmt)).scalars()]

    async def payments_total(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Decimal:
        """Sum every payment registered for the order (0 when none)."""
        stmt = select(func.coalesce(func.sum(OrderPaymentModel.amount), 0)).where(
            OrderPaymentModel.tenant_id == tenant_id,
            OrderPaymentModel.order_id == order_id,
        )
        return Decimal(str((await self._session.execute(stmt)).scalar_one()))

    # --- Payment claims (lo que el cliente DICE que pagó) -------------------
    # Ninguno de estos métodos toca `order_payments` ni recalcula el pedido. Es la propiedad
    # que hace segura toda la funcionalidad: una declaración no es dinero en ninguna consulta.
    async def create_payment_claim(
        self, claim: OrderPaymentClaim
    ) -> OrderPaymentClaim:
        model = OrderPaymentClaimModel(
            tenant_id=claim.tenant_id,
            branch_id=claim.branch_id,
            order_id=claim.order_id,
            amount=claim.amount,
            method=claim.method,
            proof_url=claim.proof_url,
            status=claim.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _payment_claim(model)

    async def list_payment_claims(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> list[OrderPaymentClaim]:
        stmt = (
            select(OrderPaymentClaimModel)
            .where(
                OrderPaymentClaimModel.tenant_id == tenant_id,
                OrderPaymentClaimModel.order_id == order_id,
            )
            .order_by(OrderPaymentClaimModel.created_at)
        )
        return [
            _payment_claim(m) for m in (await self._session.execute(stmt)).scalars()
        ]

    async def count_pending_payment_claims(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> int:
        """Cuántas esperan a una persona. Sin traerse las imágenes: esto se pregunta mucho."""
        stmt = select(func.count()).where(
            OrderPaymentClaimModel.tenant_id == tenant_id,
            OrderPaymentClaimModel.order_id == order_id,
            OrderPaymentClaimModel.status == CLAIM_PENDING,
        )
        return int((await self._session.execute(stmt)).scalar_one())

    async def get_payment_claim(
        self, tenant_id: uuid.UUID, claim_id: uuid.UUID
    ) -> OrderPaymentClaim | None:
        stmt = select(OrderPaymentClaimModel).where(
            OrderPaymentClaimModel.tenant_id == tenant_id,
            OrderPaymentClaimModel.id == claim_id,
        )
        model = (await self._session.execute(stmt)).scalar_one_or_none()
        return _payment_claim(model) if model else None

    async def resolve_payment_claims(
        self,
        tenant_id: uuid.UUID,
        order_id: uuid.UUID,
        *,
        status: str,
        employee_id: uuid.UUID | None,
        reason: str | None = None,
        claim_id: uuid.UUID | None = None,
    ) -> list[OrderPaymentClaim]:
        """Resuelve las pendientes del pedido (o una concreta) y devuelve las que cambiaron.

        Devuelve lo resuelto, no un contador, porque quien llama tiene que poder avisarle al
        cliente de cada una — y con qué motivo.
        """
        filters = [
            OrderPaymentClaimModel.tenant_id == tenant_id,
            OrderPaymentClaimModel.order_id == order_id,
            OrderPaymentClaimModel.status == CLAIM_PENDING,
        ]
        if claim_id is not None:
            filters.append(OrderPaymentClaimModel.id == claim_id)
        pending = list(
            (
                await self._session.execute(select(OrderPaymentClaimModel).where(*filters))
            ).scalars()
        )
        if not pending:
            return []
        now = datetime.now(UTC)
        for model in pending:
            model.status = status
            model.rejection_reason = reason
            model.resolved_by_employee_id = employee_id
            model.resolved_at = now
        await self._session.commit()
        return [_payment_claim(m) for m in pending]

    # --- Refunds -----------------------------------------------------------
    async def create_refund(self, refund: OrderRefund) -> OrderRefund:
        model = OrderRefundModel(
            tenant_id=refund.tenant_id,
            branch_id=refund.branch_id,
            order_id=refund.order_id,
            amount=refund.amount,
            method=refund.method,
            status=refund.status,
        )
        self._session.add(model)
        await self._session.commit()
        await self._session.refresh(model)
        return _refund(model)

    async def get_refund(
        self, tenant_id: uuid.UUID, refund_id: uuid.UUID
    ) -> OrderRefund | None:
        stmt = select(OrderRefundModel).where(
            OrderRefundModel.id == refund_id, OrderRefundModel.tenant_id == tenant_id
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _refund(row) if row else None

    async def refund_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> OrderRefund | None:
        stmt = select(OrderRefundModel).where(
            OrderRefundModel.order_id == order_id,
            OrderRefundModel.tenant_id == tenant_id,
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        return _refund(row) if row else None

    async def list_refunds(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        *,
        status: str | None = None,
    ) -> list[OrderRefund]:
        stmt = (
            select(OrderRefundModel)
            .where(
                OrderRefundModel.tenant_id == tenant_id,
                OrderRefundModel.branch_id == branch_id,
            )
            .order_by(OrderRefundModel.created_at)
        )
        if status is not None:
            stmt = stmt.where(OrderRefundModel.status == status)
        return [_refund(m) for m in (await self._session.execute(stmt)).scalars()]

    async def resolve_refund(
        self,
        tenant_id: uuid.UUID,
        refund_id: uuid.UUID,
        *,
        status: str,
        employee_id: uuid.UUID,
        reason: str | None,
    ) -> OrderRefund | None:
        # Condicional sobre `pending`: dos confirmaciones simultáneas no pueden crear dos
        # movimientos de caja por la misma devolución.
        stmt = (
            update(OrderRefundModel)
            .where(
                OrderRefundModel.id == refund_id,
                OrderRefundModel.tenant_id == tenant_id,
                OrderRefundModel.status == "pending",
            )
            .values(
                status=status,
                resolved_by_employee_id=employee_id,
                resolved_at=datetime.now(UTC),
                reason=reason,
            )
        )
        result = cast("CursorResult[Any]", await self._session.execute(stmt))
        await self._session.commit()
        if result.rowcount == 0:
            return None
        return await self.get_refund(tenant_id, refund_id)

    async def register_refund_movement(self, refund: OrderRefund) -> None:
        """Salida de caja por el monto devuelto, con el método ORIGINAL.

        Se apunta a la sesión abierta del momento en que se confirma, no a la del pedido: la
        plata sale cuando alguien hace la transferencia de vuelta, y ese es el turno que debe
        registrarlo.
        """
        session = await self.get_open_cash_session(refund.tenant_id, refund.branch_id)
        if session is None or session.id is None:
            raise ConflictError(
                "No hay sesión de caja abierta para registrar la devolución."
            )
        self._session.add(
            CashMovementModel(
                tenant_id=refund.tenant_id,
                branch_id=refund.branch_id,
                cash_session_id=session.id,
                type="out",
                category="other",
                concept="refund",
                amount=refund.amount,
                method=refund.method,
                reference_id=refund.order_id,
            )
        )
        await self._session.commit()

    async def create_order_credit(
        self,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        amount: Decimal,
        order_id: uuid.UUID,
    ) -> None:
        """Record the unpaid remainder of a closed order as a pending customer credit.

        Reaches across into the customers module's table directly (like
        `consume_inventory_for_order` writes inventory), rather than depending on
        the customers application service. The order's `customer_id` is already a
        valid FK, so no existence guard is needed here.
        """
        self._session.add(
            CustomerCreditModel(
                tenant_id=tenant_id,
                customer_id=customer_id,
                total_amount=amount,
                payment_status="pending",
                reference_id=order_id,
            )
        )
        await self._session.commit()

    # --- Inventory deduction (orders ↔ recipes ↔ inventory) ----------------
    async def consume_inventory_for_order(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> None:
        """Deduct each non-cancelled item's recipe ingredients from stock.

        Idempotent (skips if `sale` movements already exist for the order),
        non-blocking (stock may go negative), and atomic (single commit).
        """
        already = (
            await self._session.execute(
                select(InventoryMovementModel.id).where(
                    InventoryMovementModel.tenant_id == tenant_id,
                    InventoryMovementModel.reference_id == order_id,
                    InventoryMovementModel.reason == "sale",
                )
            )
        ).first()
        if already is not None:
            return

        order = await self._get_order_model(tenant_id, order_id)
        if order is None:
            return

        items = (
            await self._session.execute(
                select(OrderItemModel).where(
                    OrderItemModel.tenant_id == tenant_id,
                    OrderItemModel.order_id == order_id,
                    OrderItemModel.status != _CANCELLED,
                )
            )
        ).scalars().all()

        for item in items:
            recipe_items = (
                await self._session.execute(
                    select(RecipeItemModel).where(
                        RecipeItemModel.tenant_id == tenant_id,
                        RecipeItemModel.product_variant_id == item.product_variant_id,
                    )
                )
            ).scalars().all()
            for line in recipe_items:
                consumed = line.quantity * item.quantity
                stock = (
                    await self._session.execute(
                        select(InventoryStockModel).where(
                            InventoryStockModel.tenant_id == tenant_id,
                            InventoryStockModel.branch_id == order.branch_id,
                            InventoryStockModel.ingredient_id == line.ingredient_id,
                        )
                    )
                ).scalar_one_or_none()
                if stock is None:
                    stock = InventoryStockModel(
                        tenant_id=tenant_id,
                        branch_id=order.branch_id,
                        ingredient_id=line.ingredient_id,
                        current_quantity=-consumed,
                        min_stock=Decimal(0),
                    )
                    self._session.add(stock)
                else:
                    stock.current_quantity = stock.current_quantity - consumed
                self._session.add(
                    InventoryMovementModel(
                        tenant_id=tenant_id,
                        branch_id=order.branch_id,
                        ingredient_id=line.ingredient_id,
                        type="out",
                        reason="sale",
                        quantity=consumed,
                        employee_id=order.employee_id,
                        reference_id=order_id,
                    )
                )

        await self._commit()
