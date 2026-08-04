"""Editar el propio pedido desde el enlace. El cliente decide; esto sólo comprueba.

La forma del método es la decisión importante: **primero se proyecta, después se escribe**.

    resolver token → leer hechos → proyectar el total → juzgar → recién ahí mutar

Proyectar es calcular cuánto costaría el pedido si la edición se aplicara, sin tocar nada. Es
lo que permite rechazar sin dejar rastro, y es obligatorio aquí por un motivo concreto: la
invariante se comprueba sobre el RESULTADO, y un cambio de producto pasa por un intermedio en
el que el total baja. Si se mutara y luego se juzgara, habría que deshacer — y deshacer a
medias es cómo un pedido acaba con la gaseosa quitada y la nueva sin poner.

Todo lo que decide se relee AQUÍ, en el momento de escribir. Lo que la vista pintó hace veinte
minutos no autoriza nada: entre pintar y confirmar el cocinero pudo empezar.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Protocol

from restaurante.modules.orders.application.use_cases.manage_orders import (
    ITEM_CANCELLED,
    OrderService,
)
from restaurante.modules.orders.domain.entities import Order, OrderItem
from restaurante.modules.storefront.domain.errors import OrderEditRefused
from restaurante.modules.storefront.domain.order_edit import (
    EditRefusal,
    OrderFacts,
    item_window,
    order_window,
    paid_line_change,
    total_invariant,
)
from restaurante.modules.storefront.domain.ports import StorefrontRepository
from restaurante.shared.domain.audit import AuditEvent, AuditEventRecorder
from restaurante.shared.domain.errors import NotFoundError, ValidationError

#: Verbo del rastro. Con punto, como el resto (`login.success`), para que el filtro por
#: prefijo del módulo de auditoría agrupe todo lo que venga del storefront.
ORDER_EDITED = "storefront.order_edited"


class OrderEditReader(Protocol):
    """Los hechos que este caso de uso necesita de cocina, domicilios y pagos."""

    async def pending_payment_proof(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> bool: ...

    async def station_statuses(
        self, tenant_id: uuid.UUID, order_item_id: uuid.UUID
    ) -> list[str]: ...

    async def delivery_status(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> str | None: ...

    async def paid_total(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID
    ) -> Decimal: ...


class KitchenDispatch(Protocol):
    """Enviar a cocina lo que se añadió. Opcional: sin él, no se enruta nada."""

    async def route_order(self, tenant_id: uuid.UUID, order_id: uuid.UUID) -> None: ...


@dataclass
class AddLine:
    """Algo nuevo que el cliente quiere en su pedido."""

    variant_id: uuid.UUID
    quantity: int = 1
    addon_ids: list[uuid.UUID] = field(default_factory=list)
    removed_ingredients: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class EditLine:
    """Un cambio sobre una línea que ya existe.

    Todo opcional: lo que no se manda, no se toca. `quantity` sólo puede subir y `variant_id`
    sólo se acepta sin pago — pero eso no lo decide esta estructura, lo deciden las reglas.
    """

    item_id: uuid.UUID
    quantity: int | None = None
    add_addon_ids: list[uuid.UUID] = field(default_factory=list)
    #: Exclusiones elegidas por el cliente. El servidor compone la nota; nunca se acepta la
    #: cadena ya montada, que es como se pierde lo que ya decía.
    removed_ingredients: list[str] | None = None
    note: str | None = None
    variant_id: uuid.UUID | None = None


@dataclass
class EditCommand:
    add: list[AddLine] = field(default_factory=list)
    edit: list[EditLine] = field(default_factory=list)


@dataclass
class EditOutcome:
    """Lo que hay que poder decirle al cliente antes de que le cobren."""

    order: Order
    total_before: Decimal
    total_after: Decimal
    outstanding: Decimal


@dataclass
class ViewAddon:
    id: uuid.UUID
    name: str
    price: Decimal


@dataclass
class ViewLine:
    """Una línea del pedido tal y como el cliente tiene que verla.

    Lleva su propio veredicto: lo que no se puede tocar se pinta inerte y **explicado**, y para
    explicarlo hace falta el motivo, no un booleano.
    """

    item_id: uuid.UUID
    variant_id: uuid.UUID
    name: str
    quantity: int
    unit_price: Decimal
    line_subtotal: Decimal
    status: str
    addons: list[ViewAddon]
    #: Exclusiones ya elegidas, separadas de la nota libre: la vista las pinta como casillas
    #: marcadas y nadie tiene que reescribir lo que ya decía.
    removed_ingredients: list[str]
    note: str | None
    #: Lo que se le PUEDE quitar a este producto, para pintar las casillas sin marcar.
    removable_ingredients: list[str]
    refusal: EditRefusal | None


@dataclass
class OrderView:
    """El pedido entero detrás del enlace: qué hay, cuánto es y qué se deja cambiar."""

    order: Order
    total: Decimal
    paid: Decimal
    outstanding: Decimal
    #: Motivo por el que el pedido COMPLETO ya no admite cambios, o `None`.
    refusal: EditRefusal | None
    lines: list[ViewLine]
    #: Con quién hablar para lo que esta vista no hace (quitar, bajar, cancelar).
    contact_phone: str | None = None
    #: Cómo dijo el cliente que iba a pagar. Es una INTENCIÓN, no un pago recibido, y aun así
    #: manda: quien eligió transferencia no puede leer "se paga al recibir" cuando el total
    #: sube, porque entonces no sabe qué hacer con la diferencia.
    payment_method: str | None = None
    #: Mandó un comprobante y nadie lo ha mirado todavía.
    payment_proof_pending: bool = False


_REFUSAL_TEXT = {
    "order_closed": "Ese pedido ya está cerrado.",
    "out_of_reach": "Tu pedido ya salió; para cualquier cambio te atiende una persona.",
    "item_started": "Ya están preparando eso, así que no se puede cambiar.",
    "total_would_drop": "Quitar o reducir lo resuelve una persona, no esta pantalla.",
    "paid_line": "Eso ya está pagado: se puede añadir encima, pero no cambiarlo.",
    # Una línea cancelada no la cancela el cliente (no puede), así que verla sin poder tocarla
    # es información, no una negativa: alguien del local la quitó.
    "item_cancelled": "Esto lo quitó el restaurante.",
}

REFUSAL_ITEM_CANCELLED = EditRefusal("item_cancelled")


def refusal_text(refusal: EditRefusal | None) -> str | None:
    """La frase de un motivo. `None` cuando no hay motivo que explicar."""
    return None if refusal is None else _REFUSAL_TEXT[str(refusal)]


class OrderEditService:
    def __init__(
        self,
        repo: StorefrontRepository,
        orders: OrderService,
        reader: OrderEditReader,
        kitchen: KitchenDispatch | None = None,
        audit: AuditEventRecorder | None = None,
    ) -> None:
        self._repo = repo
        self._orders = orders
        self._reader = reader
        # Sin cocina enchufada no se enruta: lo añadido queda pendiente y lo manda el personal,
        # que es exactamente como se comporta hoy un pedido de la carta.
        self._kitchen = kitchen
        self._audit = audit

    # --- Lectura ------------------------------------------------------------
    async def load(self, tenant_id: uuid.UUID, token: str) -> tuple[Order, list[OrderItem]]:
        order = await self._orders.order_for_edit_token(tenant_id, token)
        if order is None or order.id is None:
            # Vencido, desconocido, de otro tenant: lo mismo. Distinguirlos convertiría esto
            # en un oráculo para averiguar qué pedidos existen.
            raise NotFoundError("Este enlace ya no sirve.")
        return order, await self._orders.get_order_items(tenant_id, order.id)

    async def facts(self, order: Order) -> OrderFacts:
        assert order.id is not None
        return OrderFacts(
            status=order.status,
            kitchen_state=order.kitchen_state,
            delivery_status=await self._reader.delivery_status(
                order.tenant_id, order.id
            ),
            total=order.total,
            paid=await self._reader.paid_total(order.tenant_id, order.id),
        )

    async def view(self, tenant_id: uuid.UUID, token: str) -> OrderView:
        """El pedido entero para pintarlo, con un veredicto por línea.

        El veredicto se calcula AQUÍ y no en el front por la misma razón por la que se
        recalcula al escribir: es el servidor quien sabe si la plancha ya empezó. Lo que la
        vista recibe es una foto, y una foto envejece — por eso `apply` no se fía de ella.
        """
        order, items = await self.load(tenant_id, token)
        assert order.id is not None
        facts = await self.facts(order)
        closed = order_window(facts)

        variants = await self._repo.describe_variants(
            tenant_id, [item.product_variant_id for item in items]
        )
        addons_by_item = {
            item.id: await self._orders.list_item_addons(tenant_id, item.id)
            for item in items
            if item.id is not None
        }
        names = await self._repo.addon_names(
            tenant_id,
            [addon.addon_id for addons in addons_by_item.values() for addon in addons],
        )

        lines: list[ViewLine] = []
        for item in items:
            assert item.id is not None
            variant = variants.get(item.product_variant_id)
            removable = variant.removable_ingredients if variant else []
            removed, note = split_note(item.notes, removable)
            if item.status == ITEM_CANCELLED:
                refusal: EditRefusal | None = REFUSAL_ITEM_CANCELLED
            else:
                refusal = closed or item_window(
                    await self._reader.station_statuses(tenant_id, item.id)
                )
            lines.append(
                ViewLine(
                    item_id=item.id,
                    variant_id=item.product_variant_id,
                    name=variant.product_name if variant else "",
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    line_subtotal=item.line_subtotal,
                    status=item.status,
                    addons=[
                        ViewAddon(
                            id=addon.addon_id,
                            name=names.get(addon.addon_id, ""),
                            price=addon.applied_price,
                        )
                        for addon in addons_by_item.get(item.id, [])
                    ],
                    removed_ingredients=removed,
                    note=note,
                    removable_ingredients=list(removable),
                    refusal=refusal,
                )
            )

        return OrderView(
            order=order,
            total=facts.total,
            paid=facts.paid,
            outstanding=max(Decimal(0), facts.total - facts.paid),
            refusal=closed,
            lines=lines,
            contact_phone=await self._repo.branch_phone(tenant_id, order.branch_id),
            payment_method=order.payment_method,
            payment_proof_pending=await self._reader.pending_payment_proof(
                tenant_id, order.id
            ),
        )

    # --- Edición ------------------------------------------------------------
    async def apply(
        self,
        tenant_id: uuid.UUID,
        token: str,
        command: EditCommand,
        *,
        ip: str | None = None,
    ) -> EditOutcome:
        order, items = await self.load(tenant_id, token)
        assert order.id is not None
        by_id: dict[uuid.UUID, OrderItem] = {
            item.id: item for item in items if item.id is not None
        }

        facts = await self.facts(order)
        _refuse_if(order_window(facts))

        # 1. Se resuelve TODO contra el catálogo antes de escribir nada. El precio nunca viene
        #    del cliente: `add_item` lo recibe de quien llama, así que quien llama tiene que
        #    ser quien lo busca.
        additions = [await self._price_addition(tenant_id, order, line) for line in command.add]
        edits = [
            await self._price_edit(tenant_id, order, by_id, change)
            for change in command.edit
        ]

        # 2. Las ventanas por ítem, sobre lo que se va a tocar.
        for change in command.edit:
            _refuse_if(
                item_window(
                    await self._reader.station_statuses(tenant_id, change.item_id)
                )
            )

        # 3. Las líneas pagadas no cambian de identidad.
        for change in command.edit:
            _refuse_if(
                paid_line_change(facts, changes_line_identity=change.variant_id is not None)
            )

        # 4. La invariante, sobre el pedido PROYECTADO.
        delta = sum((a.delta for a in additions), Decimal(0)) + sum(
            (e.delta for e in edits), Decimal(0)
        )
        _refuse_if(total_invariant(facts.total, facts.total + delta))

        # 5. Recién ahora se escribe. Nada de lo anterior dejó rastro.
        for addition in additions:
            await self._write_addition(tenant_id, order, addition)
        for priced in edits:
            await self._write_edit(tenant_id, priced)

        updated = await self._orders.get_order(tenant_id, order.id)

        # 6. Lo añadido se manda a cocina si el resto ya está allí. Un ítem que se factura sin
        #    cocinarse es peor que no haber dejado añadir.
        if additions and self._kitchen is not None and order.kitchen_state != "none":
            await self._kitchen.route_order(tenant_id, order.id)

        # 7. Y queda dicho quién lo pidió. Firma el empleado de sistema porque la comanda
        #    necesita un empleado y el cliente no lo es; el rastro aclara que la firma es del
        #    sistema y la decisión del cliente, que es lo que hay que poder contestar cuando
        #    alguien pregunte "¿y esto quién lo puso?".
        await self._record_edit(order, facts.total, updated.total, command, ip)

        paid = await self._reader.paid_total(tenant_id, order.id)
        return EditOutcome(
            order=updated,
            total_before=facts.total,
            total_after=updated.total,
            outstanding=max(Decimal(0), updated.total - paid),
        )

    async def _record_edit(
        self,
        order: Order,
        before: Decimal,
        after: Decimal,
        command: EditCommand,
        ip: str | None,
    ) -> None:
        if self._audit is None:
            return
        # Nunca el token: es la credencial con la que se entró, y un rastro que la copia
        # convierte el registro de auditoría en la llave de todos los pedidos que describe.
        detail = (
            f"canal=enlace_cliente firmante=pedidos_web "
            f"añadidas={len(command.add)} cambiadas={len(command.edit)} "
            f"total={before:.2f}->{after:.2f}"
        )
        await self._audit.record(
            AuditEvent(
                tenant_id=order.tenant_id,
                action=ORDER_EDITED,
                actor_id=order.employee_id,
                entity_type="order",
                entity_id=order.id,
                branch_id=order.branch_id,
                ip=ip,
                detail=detail[:512],
            )
        )

    # --- Interno ------------------------------------------------------------
    async def _price_addition(
        self, tenant_id: uuid.UUID, order: Order, line: AddLine
    ) -> _PricedAddition:
        if line.quantity <= 0:
            raise ValidationError("La cantidad debe ser positiva.")
        product_id = await self._repo.sellable_variant_product(tenant_id, line.variant_id)
        if product_id is None:
            raise ValidationError("Ese producto ya no está disponible.")
        unit = await self._repo.product_price(tenant_id, product_id, order.branch_id)
        unit = unit if unit is not None else Decimal(0)
        addons: list[tuple[uuid.UUID, Decimal]] = []
        for addon_id in line.addon_ids:
            price = await self._repo.addon_price(tenant_id, addon_id)
            if price is None:
                raise ValidationError("Esa adición ya no está disponible.")
            addons.append((addon_id, price))
        delta = unit * line.quantity + sum((p for _, p in addons), Decimal(0))
        return _PricedAddition(line=line, unit_price=unit, addons=addons, delta=delta)

    async def _price_edit(
        self,
        tenant_id: uuid.UUID,
        order: Order,
        by_id: dict[uuid.UUID, OrderItem],
        change: EditLine,
    ) -> _PricedEdit:
        item = by_id.get(change.item_id)
        if item is None:
            raise NotFoundError("Ese producto no está en tu pedido.")

        delta = Decimal(0)
        unit_price = item.unit_price

        if change.variant_id is not None:
            product_id = await self._repo.sellable_variant_product(
                tenant_id, change.variant_id
            )
            if product_id is None:
                raise ValidationError("Ese producto ya no está disponible.")
            price = await self._repo.product_price(tenant_id, product_id, order.branch_id)
            unit_price = price if price is not None else Decimal(0)
            delta += (unit_price - item.unit_price) * item.quantity

        if change.quantity is not None:
            if change.quantity < item.quantity:
                # Se rechaza aquí y no en la invariante para poder decir por qué: bajar es lo
                # que crea devoluciones, y el motivo se explica distinto que "bajaría el total".
                raise OrderEditRefused(
                    EditRefusal("total_would_drop"), _REFUSAL_TEXT["total_would_drop"]
                )
            delta += unit_price * (change.quantity - item.quantity)

        addons: list[tuple[uuid.UUID, Decimal]] = []
        for addon_id in change.add_addon_ids:
            price = await self._repo.addon_price(tenant_id, addon_id)
            if price is None:
                raise ValidationError("Esa adición ya no está disponible.")
            addons.append((addon_id, price))
            delta += price

        return _PricedEdit(
            change=change,
            item=item,
            unit_price=unit_price,
            addons=addons,
            delta=delta,
        )

    async def _write_addition(
        self, tenant_id: uuid.UUID, order: Order, addition: _PricedAddition
    ) -> None:
        assert order.id is not None
        item = await self._orders.add_item(
            tenant_id,
            order.id,
            addition.line.variant_id,
            addition.line.quantity,
            addition.unit_price,
            notes=compose_note(addition.line.removed_ingredients, addition.line.note),
        )
        assert item.id is not None
        for addon_id, price in addition.addons:
            await self._orders.attach_addon(tenant_id, item.id, addon_id, price)

    async def _write_edit(self, tenant_id: uuid.UUID, change: _PricedEdit) -> None:
        edit = change.change
        if edit.variant_id is not None:
            await self._orders.change_item_variant(
                tenant_id, edit.item_id, edit.variant_id, change.unit_price
            )
        if edit.quantity is not None:
            await self._orders.update_item_quantity(tenant_id, edit.item_id, edit.quantity)
        for addon_id, price in change.addons:
            await self._orders.attach_addon(tenant_id, edit.item_id, addon_id, price)
        if edit.removed_ingredients is not None or edit.note is not None:
            await self._orders.set_item_notes(
                tenant_id,
                edit.item_id,
                compose_note(edit.removed_ingredients or [], edit.note),
            )


@dataclass
class _PricedAddition:
    line: AddLine
    unit_price: Decimal
    addons: list[tuple[uuid.UUID, Decimal]]
    delta: Decimal


@dataclass
class _PricedEdit:
    change: EditLine
    item: OrderItem
    unit_price: Decimal
    addons: list[tuple[uuid.UUID, Decimal]]
    delta: Decimal


def compose_note(removed_ingredients: list[str], note: str | None) -> str | None:
    """`Sin X · Sin Y · <nota>`. La compone el SERVIDOR, no el cliente.

    Es la misma función que usa el checkout al pedir, y está aquí por la misma razón por la
    que no se acepta la cadena ya montada: el cliente elige exclusiones, no escribe la nota
    entera. Aceptarla escrita es cómo se pierde el "tocar timbre, bebé dormido" que ya estaba.
    """
    parts = [f"Sin {name.strip()}" for name in removed_ingredients if name.strip()]
    cleaned = (note or "").strip()
    if cleaned:
        parts.append(cleaned)
    return " · ".join(parts) if parts else None


def split_note(note: str | None, removable_ingredients: list[str]) -> tuple[list[str], str | None]:
    """La inversa de `compose_note`: de la cadena guardada, exclusiones y texto libre.

    Existe porque la vista tiene que enseñar las exclusiones YA elegidas como casillas
    marcadas. Sin esto, el cliente que quiere quitar el tomate reescribe la nota entera y se
    lleva por delante el "tocar timbre, bebé dormido" que ya estaba.

    Un trozo cuenta como exclusión sólo si es exactamente `Sin <algo del catálogo>`. Cotejar
    contra el catálogo y no contra el prefijo es lo que evita que una nota libre que empieza
    por "Sin" se convierta en una casilla que nadie escribió.
    """
    if not note:
        return [], None
    known = {f"Sin {name.strip()}": name.strip() for name in removable_ingredients}
    removed: list[str] = []
    rest: list[str] = []
    for raw in note.split(" · "):
        part = raw.strip()
        if part in known:
            removed.append(known[part])
        elif part:
            rest.append(part)
    return removed, (" · ".join(rest) or None)


def _refuse_if(refusal: EditRefusal | None) -> None:
    if refusal is not None:
        raise OrderEditRefused(refusal, _REFUSAL_TEXT[str(refusal)])
