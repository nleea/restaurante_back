"""Application service for the public Storefront module.

Two customer-facing capabilities, composed from the vetted staff use cases so the
public path behaves exactly like a staff order (inventory, KDS, dispatch all unchanged):

- ``get_menu`` — the customer-safe menu read-model for a branch.
- ``create_order`` — turn a cart into a real, OPEN/unpaid order left **pending** (items
  NOT auto-fired; staff confirm and fire). The chosen payment method is stored as an
  intent (``orders.payment_method``); no ``order_payments`` row is created at intake.

Both take the branch as an **argument**, resolved by the caller through
``resolve_branch``. The branch therefore comes from the URL path and never from the
request body: a customer cannot redirect their order to another kitchen by editing the
payload, and the menu they saw is the branch they ordered from.

Everything that can make the request invalid (empty/blank fields, unknown or non-sellable
variants, unknown addons, missing delivery address) is checked BEFORE any write, so a
rejected intake (422) leaves nothing half-created.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from restaurante.modules.customers.application.use_cases.manage_customers import (
    CustomerService,
)
from restaurante.modules.delivery.application.use_cases.manage_delivery import (
    DeliveryService,
)
from restaurante.modules.orders.application.use_cases.manage_orders import OrderService
from restaurante.modules.orders.domain.entities import Order
from restaurante.modules.storefront.domain.entities import (
    StoreBranch,
    StoreMenu,
    StoreTable,
)
from restaurante.modules.storefront.domain.ports import (
    DeliveryReadiness,
    KitchenDispatch,
    StorefrontRepository,
)
from restaurante.shared.customer_channel.ports import (
    CUSTOMER_STATE_AWAITING_PROOF,
    CUSTOMER_STATE_ORDER_RECEIVED,
    ChannelContact,
    CustomerChannelDirectory,
    CustomerNotifier,
)
from restaurante.shared.domain.errors import (
    BranchNotFoundError,
    TableNotFoundError,
    ValidationError,
)

_PICKUP = "pickup"
_DELIVERY = "delivery"
_CHANNEL_PICKUP = "takeaway"
_CHANNEL_DINE_IN = "dine_in"
# El sello que distingue "el cliente escaneó el QR de su mesa" de "el mesero lo tomó". Mismo
# canal, mismo empleado de sistema, misma mesa: sin el sello son indistinguibles.
_ORIGIN_QR = "qr"
# El único método que NO deja el pedido debiendo: se cobra en la puerta. Cualquier otro nace
# prepago y sin verificar, y por eso su acuse es otro.
_METHOD_CASH = "cash"
_CHANNEL_DELIVERY = "delivery"

# Lo que el CLIENTE lee cuando la sede no puede cotizar. NO dice "sin bandas de tarifa": ese es
# un problema del negocio y no le toca cargarlo. Dice lo único que le sirve — hoy no, y qué
# puede hacer en su lugar.
NOT_TAKING_DELIVERIES = (
    "Ahora mismo no estamos tomando pedidos a domicilio. "
    "Puedes hacer tu pedido para recoger, o escribirnos por WhatsApp."
)


@dataclass
class OrderLineCommand:
    variant_id: uuid.UUID
    quantity: int
    addon_ids: list[uuid.UUID] = field(default_factory=list)
    removed_ingredients: list[str] = field(default_factory=list)
    note: str | None = None


@dataclass
class TableOrderCommand:
    """Lo que el comensal manda al confirmar desde el QR de su mesa.

    No trae teléfono ni tipo de entrega, y eso NO es una simplificación: no hay nada que
    entregar —la comida sale a la mesa que ya venía en la URL— y pedir un teléfono para almorzar
    es fricción que nadie acepta sentado. Tampoco trae método de pago: se paga al cerrar.
    """

    diner_name: str
    lines: list[OrderLineCommand]


@dataclass
class StorefrontOrderCommand:
    customer_name: str
    customer_phone: str
    fulfillment_type: str
    # Opcional desde la cotización dinámica de domicilio: un domicilio NO sabe todavía cuánto
    # cuesta, así que pedirle al cliente que elija cómo pagar un total que aún no existe es
    # pedirle que decida a ciegas. Lo elige después, desde el enlace de pago que le llega por
    # WhatsApp con el total ya cotizado. Recoger en tienda sigue exigiéndolo: ahí no hay nada
    # que esperar y el total del carrito ya es el definitivo.
    payment_method: str | None
    lines: list[OrderLineCommand]
    address_text: str | None = None
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    reference: str | None = None
    # Token del enlace que llegó por WhatsApp. Opcional SIEMPRE: el pedido se crea igual
    # sin él, con él vencido o con uno de otra sede. Precarga y ata; nunca autentica.
    store_token: str | None = None


def _coord(value: Decimal) -> str:
    """Cinco decimales ≈ 1 m: suficiente para llegar, y legible en una comanda impresa."""
    return f"{value:.5f}"


@dataclass
class _ResolvedLine:
    """A cart line proven valid, with the prices to charge, ready to persist."""

    command: OrderLineCommand
    unit_price: Decimal
    addon_prices: list[tuple[uuid.UUID, Decimal]]


class StorefrontService:
    def __init__(
        self,
        repo: StorefrontRepository,
        order_service: OrderService,
        customer_service: CustomerService,
        delivery_service: DeliveryService,
        channel_directory: CustomerChannelDirectory | None = None,
        customer_notifier: CustomerNotifier | None = None,
        delivery_readiness: DeliveryReadiness | None = None,
        kitchen: KitchenDispatch | None = None,
    ) -> None:
        self._repo = repo
        self._orders = order_service
        self._customers = customer_service
        self._delivery = delivery_service
        # Puertos opcionales hacia el canal del cliente. Ausentes → el storefront se
        # comporta exactamente como antes: sin precarga, sin enlace y sin avisos.
        self._channel = channel_directory
        self._customer_notifier = customer_notifier
        # Sin él se acepta todo, como antes. Con él, una sede que no puede cotizar un domicilio
        # lo dice ANTES de tomarlo, en vez de dejar al cliente esperando un enlace imposible.
        self._delivery_readiness = delivery_readiness
        # Sólo lo usa el pedido de mesa. Opcional como los demás puertos de salida: sin él, la
        # carta pública sigue sirviendo exactamente igual y el pedido de mesa queda pendiente,
        # que es el comportamiento del resto del storefront.
        self._kitchen = kitchen

    async def resolve_store_token(
        self, tenant_id: uuid.UUID, token: str
    ) -> ChannelContact | None:
        """El contacto dueño del token, sólo si es de ESTE negocio.

        El token es global (lo emite una conversación, no un tenant), así que el filtro
        de tenant se aplica aquí: un enlace de otro negocio en este subdominio no debe
        siquiera confirmar que existe.
        """
        if self._channel is None or not token:
            return None
        contact = await self._channel.resolve_store_token(token)
        if contact is None or contact.tenant_id != tenant_id:
            return None
        return contact

    async def resolve_branch(
        self, tenant_id: uuid.UUID, code: str | None
    ) -> uuid.UUID | None:
        """Branch addressed by ``code``, or the primary branch when no code is given.

        Raises `BranchNotFoundError` for a code that matches no active branch. It must
        NEVER fall back to the primary branch: the customer believing they ordered from
        Centro while the ticket prints in Norte is not recoverable, and a 404 is.
        """
        if code is None:
            return await self._repo.get_primary_branch_id(tenant_id)
        branch_id = await self._repo.get_branch_id_by_code(tenant_id, code)
        if branch_id is None:
            raise BranchNotFoundError(f"Sucursal no encontrada: {code}")
        return branch_id

    async def list_branches(self, tenant_id: uuid.UUID) -> list[StoreBranch]:
        """Active branches for the public picker."""
        return await self._repo.list_active_branches(tenant_id)

    async def resolve_table(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID, code: str
    ) -> StoreTable:
        """La mesa detrás del QR. Lectura pura: escanear NO ocupa la mesa.

        Ocuparla aquí dejaría marcada como ocupada cualquier mesa que alguien escanee de paso
        —sin nadie sentado— y el Salón la retiraría del servicio. Una mesa se ocupa cuando hay
        comida en camino, y eso pasa al confirmar.

        Un código desconocido, una mesa desactivada o una mesa de otra sede son lo mismo: 404.
        Nunca otra mesa.
        """
        table = await self._repo.get_active_table_by_code(tenant_id, branch_id, code)
        if table is None:
            raise TableNotFoundError(f"Mesa no encontrada: {code}")
        return table

    async def create_table_order(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        table_id: uuid.UUID,
        command: TableOrderCommand,
    ) -> Order:
        """El pedido de mesa: se crea Y SE ENVÍA A COCINA en la misma operación.

        Ésta es la excepción deliberada a la regla del storefront, que deja los pedidos
        pendientes de que el personal los confirme. La razón de aquella regla es que un pedido
        web lo hace un desconocido a distancia y el negocio quiere una mirada humana antes de
        gastar insumos. En la mesa, quien confirma está sentado en el local, delante del plato
        que va a pagar: la revisión que en el web hace el personal, aquí la hace el propio
        cliente mirando su carrito antes de pulsar «Confirmar».

        Confirmar ES el compromiso. Por eso enruta, y por eso cada confirmación posterior desde
        el enlace es otra ronda que también entra sola (`edit_order` ya lo hace).

        Sin método de pago: se paga al cerrar. El portón de pago de cocina trata un pedido sin
        método como efectivo —"su plata llega en la puerta"—, así que no hace falta ninguna
        excepción ahí.
        """
        if not command.lines:
            raise ValidationError("El pedido no tiene productos.")
        diner = command.diner_name.strip()
        if not diner:
            raise ValidationError("Falta el nombre de quien pide.")

        # Todo se valida ANTES de escribir nada: un pedido rechazado no puede dejar media
        # comanda ni un tiquete suelto en el pase.
        resolved = await self._resolve_lines(tenant_id, branch_id, command.lines)

        employee_id = await self._repo.resolve_system_employee(tenant_id, branch_id)
        order = await self._orders.open_order(
            tenant_id,
            branch_id,
            _CHANNEL_DINE_IN,
            employee_id,
            dining_table_id=table_id,
            diner_name=diner,
            origin=_ORIGIN_QR,
        )
        assert order.id is not None

        for line in resolved:
            note = self._compose_note(
                line.command.removed_ingredients, line.command.note
            )
            item = await self._orders.add_item(
                tenant_id,
                order.id,
                line.command.variant_id,
                line.command.quantity,
                line.unit_price,
                notes=note,
            )
            assert item.id is not None
            for addon_id, applied_price in line.addon_prices:
                await self._orders.attach_addon(
                    tenant_id, item.id, addon_id, applied_price
                )

        # El enlace con el que el comensal seguirá el pedido y pedirá otra ronda. Se acuña en
        # todos los caminos públicos por lo mismo: es el único momento en que sabemos con
        # certeza que quien tiene delante la pantalla es el dueño del pedido.
        await self._orders.mint_edit_token(tenant_id, order.id)

        # Y AQUÍ está la excepción, con su porqué al lado a propósito. Sin esta línea el pedido
        # se queda esperando a un mesero que en este negocio puede no existir, que es justo lo
        # que esta capacidad viene a resolver. No es una incoherencia con el resto del
        # storefront: es la diferencia entre un desconocido a distancia y alguien sentado en
        # una mesa del local.
        if self._kitchen is not None:
            await self._kitchen.route_order(tenant_id, order.id)

        refreshed = await self._orders.get_order(tenant_id, order.id)
        return refreshed if refreshed is not None else order

    async def can_take_orders(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool:
        """¿Puede esta sede recibir un pedido ahora mismo?

        Es la caja, que es el portón de verdad de `open_order`. Se consulta al resolver la mesa
        para poder decírselo al comensal ANTES del carrito: hacerle montar el pedido para
        rechazárselo en el último paso es hacerle perder el tiempo por algo que se sabía en la
        primera petición.
        """
        return await self._repo.has_open_cash_session(tenant_id, branch_id)

    async def get_menu(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID | None
    ) -> StoreMenu:
        """The customer-safe menu for the given branch (empty when there is none)."""
        if branch_id is None:
            return StoreMenu(categories=[], products=[])
        return await self._repo.build_menu(tenant_id, branch_id)

    @staticmethod
    def _intake_payment_method(
        command: StorefrontOrderCommand, is_delivery: bool
    ) -> str | None:
        """El método de pago con el que NACE el pedido, o None si aún no toca elegirlo.

        Un domicilio nace sin método a propósito. Su total todavía no existe —falta cotizar el
        domicilio— y hacer que el cliente elija cómo pagar una cifra que no ha visto es la
        clase de decisión que se cambia de opinión en la puerta. El enlace de pago recoge la
        elección después, con el total definitivo delante.

        Recoger en tienda no cambia: el total del carrito ya es el definitivo, así que seguir
        exigiéndolo no le cuesta nada al cliente y mantiene intacto el flujo de mostrador.
        """
        if is_delivery:
            return None
        if not (command.payment_method or "").strip():
            raise ValidationError("Elige un medio de pago para tu pedido.")
        return command.payment_method

    async def create_order(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID | None,
        command: StorefrontOrderCommand,
    ) -> Order:
        if not command.lines:
            raise ValidationError("El pedido no tiene productos.")
        if command.fulfillment_type not in (_PICKUP, _DELIVERY):
            raise ValidationError(
                f"Tipo de entrega inválido: {command.fulfillment_type}"
            )

        if branch_id is None:
            raise ValidationError("El negocio no tiene una sucursal principal.")

        is_delivery = command.fulfillment_type == _DELIVERY
        if is_delivery and self._delivery_readiness is not None:
            if not await self._delivery_readiness.can_take_deliveries(tenant_id, branch_id):
                raise ValidationError(NOT_TAKING_DELIVERIES)
        payment_method = self._intake_payment_method(command, is_delivery)
        address_text = self._delivery_address(command) if is_delivery else None

        # --- Validate every line BEFORE writing anything -------------------
        resolved = await self._resolve_lines(tenant_id, branch_id, command.lines)

        # --- Compose (each step is the same call staff make) ---------------
        employee_id = await self._repo.resolve_system_employee(tenant_id, branch_id)
        customer = await self._customers.find_or_create_by_phone(
            tenant_id, command.customer_name, command.customer_phone
        )
        order = await self._orders.open_order(
            tenant_id,
            branch_id,
            _CHANNEL_DELIVERY if is_delivery else _CHANNEL_PICKUP,
            employee_id,
            customer_id=customer.id,
            payment_method=payment_method,
        )
        assert order.id is not None

        for line in resolved:
            note = self._compose_note(
                line.command.removed_ingredients, line.command.note
            )
            item = await self._orders.add_item(
                tenant_id,
                order.id,
                line.command.variant_id,
                line.command.quantity,
                line.unit_price,
                notes=note,
            )
            assert item.id is not None
            for addon_id, applied_price in line.addon_prices:
                await self._orders.attach_addon(
                    tenant_id, item.id, addon_id, applied_price
                )

        if is_delivery:
            assert address_text is not None
            await self._delivery.create_delivery(
                tenant_id,
                order.id,
                address_text=address_text,
                latitude=command.latitude,
                longitude=command.longitude,
            )

        # El enlace con el que el cliente podrá corregir lo que se le olvidó. Se acuña SIEMPRE
        # y en todos los caminos públicos: es el único momento en que sabemos con certeza que
        # quien tiene delante la pantalla es el dueño del pedido.
        await self._orders.mint_edit_token(tenant_id, order.id)

        # El token ata el pedido al chat. Se hace al FINAL y sin poder fallar: un token
        # vencido, desconocido o de otra sede deja el pedido creado igual, identificado
        # por teléfono como cualquier otro. Perder el enlace cuesta un aviso, no la venta.
        await self._link_contact(tenant_id, branch_id, order.id, command.store_token)

        # Deliberately NOT firing to the kitchen, NOT registering a payment, NOT closing:
        # the order lands OPEN and pending for staff to confirm.
        #
        # El "recibimos tu pedido" sale AQUÍ y no en `open_order`: allí la comanda está
        # vacía y el total sería $0. Además es el único camino donde el pedido lo hizo el
        # propio cliente — una comanda de mostrador no le habla a nadie.
        # Un domicilio NO se acusa aquí, y es deliberado. Los dos acuses de abajo llevan
        # `Total: {order_total}` — y el total de un domicilio recién creado todavía NO incluye
        # el domicilio. Mandarlo sería decirle al cliente una cifra que vamos a contradecir un
        # minuto después con el enlace de pago, que es exactamente la discusión en la puerta
        # que esta propuesta existe para evitar. Su acuse ES ese mensaje de cotización, que
        # llega con el total verdadero (`PendingQuoter`).
        if self._customer_notifier is not None and not is_delivery:
            # Un pedido que nace prepago nace DEBIENDO: la cocina no lo va a ver hasta que una
            # persona confirme el pago, así que el acuse tiene que decir eso y no "recibido".
            # Los dos son mutuamente excluyentes — mandar los dos es el mismo hecho dos veces.
            #
            # Aquí no hace falta mirar los pagos: un pedido recién creado nunca tiene ninguno
            # (el cobro lo registra el personal después), así que el método basta.
            state = (
                CUSTOMER_STATE_ORDER_RECEIVED
                if payment_method == _METHOD_CASH
                else CUSTOMER_STATE_AWAITING_PROOF
            )
            try:
                await self._customer_notifier.notify_order_state(
                    tenant_id, order.id, state
                )
            except Exception:  # noqa: BLE001 - avisar es un efecto secundario
                pass
        # Se relee para que la respuesta lleve el token recién acuñado: `order` es de antes.
        refreshed = await self._orders.get_order(tenant_id, order.id)
        return refreshed or order

    async def _link_contact(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        order_id: uuid.UUID,
        token: str | None,
    ) -> None:
        if not token:
            return
        contact = await self.resolve_store_token(tenant_id, token)
        if contact is None or contact.branch_id != branch_id:
            # Sede distinta: el enlace era de Centro y el pedido es de Norte. Atarlo
            # mandaría los avisos por el chat equivocado, así que no se ata.
            return
        await self._repo.link_order_contact(tenant_id, order_id, contact.contact_id)

    # --- helpers -----------------------------------------------------------
    async def _resolve_lines(
        self,
        tenant_id: uuid.UUID,
        branch_id: uuid.UUID,
        lines: list[OrderLineCommand],
    ) -> list[_ResolvedLine]:
        resolved: list[_ResolvedLine] = []
        for line in lines:
            if line.quantity <= 0:
                raise ValidationError("La cantidad debe ser positiva.")
            product_id = await self._repo.sellable_variant_product(
                tenant_id, line.variant_id
            )
            if product_id is None:
                raise ValidationError(
                    f"Variante no disponible: {line.variant_id}"
                )
            price = await self._repo.product_price(tenant_id, product_id, branch_id)
            addon_prices: list[tuple[uuid.UUID, Decimal]] = []
            for addon_id in line.addon_ids:
                addon_price = await self._repo.addon_price(tenant_id, addon_id)
                if addon_price is None:
                    raise ValidationError(f"Adición no disponible: {addon_id}")
                addon_prices.append((addon_id, addon_price))
            resolved.append(
                _ResolvedLine(
                    command=line,
                    unit_price=price if price is not None else Decimal(0),
                    addon_prices=addon_prices,
                )
            )
        return resolved

    @staticmethod
    def _delivery_address(command: StorefrontOrderCommand) -> str:
        """El texto que el domiciliario lee en la puerta.

        Compartir la ubicación es una forma legítima de decir dónde vives: el pedido guarda
        el pin, el domiciliario lleva el mapa, y ese pin es MÁS preciso que cualquier
        dirección escrita (que además habría que geocodificar). Rechazar un pedido con
        coordenadas por no traer texto era pedirle al cliente que escribiera algo que el
        sistema ya sabía mejor que él.
        """
        base = (command.address_text or "").strip()
        reference = (command.reference or "").strip()
        if base and reference:
            return f"{base} ({reference})"
        if base or reference:
            return base or reference
        if command.latitude is not None and command.longitude is not None:
            # Sin texto pero con pin. Se compone una etiqueta legible para que la comanda no
            # salga en blanco y quede claro que hay que guiarse por el mapa.
            return (
                "Ubicación compartida por el cliente "
                f"({_coord(command.latitude)}, {_coord(command.longitude)})"
            )
        raise ValidationError(
            "La entrega necesita una dirección escrita o tu ubicación compartida."
        )

    @staticmethod
    def _compose_note(removed_ingredients: list[str], note: str | None) -> str | None:
        """Fold chosen removals into the kitchen note: 'Sin X · Sin Y · <note>'."""
        parts = [
            f"Sin {name.strip()}" for name in removed_ingredients if name.strip()
        ]
        cleaned_note = (note or "").strip()
        if cleaned_note:
            parts.append(cleaned_note)
        return " · ".join(parts) if parts else None
