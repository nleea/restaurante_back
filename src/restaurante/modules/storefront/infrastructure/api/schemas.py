"""Pydantic schemas for the public Storefront API.

Wire contract is camelCase and money is serialized as decimal STRINGS. Request models
accept camelCase (``addressText``, ``variantId``, ``addonIds``, ``removedIngredients``,
``paymentMethod``) via a shared ``to_camel`` alias generator.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from restaurante.modules.storefront.application.use_cases.edit_order import (
    OrderView,
    ViewLine,
    refusal_text,
)
from restaurante.modules.storefront.domain.entities import StoreMenu


class _CamelModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel, populate_by_name=True, extra="ignore"
    )


def _money(value: Decimal | None) -> str:
    """Decimal → string ('' when unpriced); mirrors the read-model contract."""
    return "" if value is None else f"{value:.2f}"


# --- Menu response ----------------------------------------------------------
class StorefrontCategoryResponse(_CamelModel):
    id: uuid.UUID
    name: str


class StorefrontAddonResponse(_CamelModel):
    id: uuid.UUID
    name: str
    price: str


class StorefrontProductResponse(_CamelModel):
    id: uuid.UUID
    category_id: uuid.UUID
    name: str
    description: str
    image_url: str
    price: str
    variant_id: uuid.UUID | None
    addons: list[StorefrontAddonResponse]
    removable_ingredients: list[str]


class StorefrontMenuResponse(_CamelModel):
    categories: list[StorefrontCategoryResponse]
    products: list[StorefrontProductResponse]

    @classmethod
    def from_menu(cls, menu: StoreMenu) -> StorefrontMenuResponse:
        return cls(
            categories=[
                StorefrontCategoryResponse(id=c.id, name=c.name)
                for c in menu.categories
            ],
            products=[
                StorefrontProductResponse(
                    id=p.id,
                    category_id=p.category_id,
                    name=p.name,
                    description=p.description or "",
                    image_url=p.image_url or "",
                    price=_money(p.price),
                    variant_id=p.variant_id,
                    addons=[
                        StorefrontAddonResponse(
                            id=a.id, name=a.name, price=_money(a.price)
                        )
                        for a in p.addons
                    ],
                    removable_ingredients=list(p.removable_ingredients),
                )
                for p in menu.products
            ],
        )


# --- Order intake request ---------------------------------------------------
# Explicit per-field aliases (not a generator): combining an `alias_generator` with
# `Field(...)` constraints trips a spurious pydantic warning, so camelCase keys are
# declared where needed and `populate_by_name` keeps snake_case accepted too.
class _RequestModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class StorefrontCustomerRequest(_RequestModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=30)


class StorefrontFulfillmentRequest(_RequestModel):
    type: Literal["pickup", "delivery"]
    address_text: str | None = Field(default=None, max_length=255, alias="addressText")
    latitude: Decimal | None = None
    longitude: Decimal | None = None
    reference: str | None = Field(default=None, max_length=255)


class StorefrontLineRequest(_RequestModel):
    variant_id: uuid.UUID = Field(alias="variantId")
    quantity: int = Field(gt=0)
    addon_ids: list[uuid.UUID] = Field(default_factory=list, alias="addonIds")
    removed_ingredients: list[str] = Field(
        default_factory=list, alias="removedIngredients"
    )
    note: str | None = Field(default=None, max_length=255)


class CreateStorefrontOrderRequest(_RequestModel):
    customer: StorefrontCustomerRequest
    fulfillment: StorefrontFulfillmentRequest
    # Opcional en el contrato, obligatorio para RECOGER. Un domicilio no lo manda: su total no
    # existe todavía. La regla vive en el caso de uso porque depende de `fulfillment`, que el
    # esquema no debería tener que correlacionar; aquí sólo deja de exigirlo siempre.
    payment_method: str | None = Field(
        default=None, max_length=30, alias="paymentMethod"
    )
    lines: list[StorefrontLineRequest] = Field(min_length=1)
    # Viaja del enlace de WhatsApp al pedido. Nunca se pinta en un campo visible: es una
    # credencial de portador, y un token en pantalla acaba en una captura compartida.
    store_token: str | None = Field(
        default=None, max_length=64, alias="storeToken"
    )


class StorefrontSessionResponse(_CamelModel):
    """A quién resuelve el token del enlace: sólo lo que precarga el checkout.

    Ni pedidos, ni historial, ni id de contacto. Un enlace filtrado no puede leer nada
    de nadie; lo peor que puede pasar es que alguien vea un nombre y un teléfono que ya
    estaban en el chat del que salió el enlace.
    """

    name: str | None
    phone: str
    branch_code: str | None


# --- Order intake response --------------------------------------------------
class StorefrontOrderResponse(_CamelModel):
    order_id: uuid.UUID
    order_number: str
    status: str
    # El token con el que este cliente vuelve a abrir SU pedido para corregirlo. Viaja aquí y
    # no en una consulta aparte porque éste es el único instante en que sabemos sin lugar a
    # dudas que quien está delante es su dueño.
    edit_token: str | None = None


class StorefrontHourWindow(_CamelModel):
    weekday: int
    open_minute: int
    close_minute: int


class StorefrontNextOpening(_CamelModel):
    weekday: int
    minute: int


class StorefrontHoursResponse(_CamelModel):
    """Public opening hours + whether open now + the next opening (for "abrimos a las X")."""

    is_open_now: bool
    next_opening: StorefrontNextOpening | None = None
    windows: list[StorefrontHourWindow]


class StorefrontBranchResponse(_CamelModel):
    """A branch as offered by the public picker. `code` addresses it in the URL."""

    id: uuid.UUID
    code: str
    name: str
    address: str | None = None
    phone: str | None = None


# --- "Mi pedido": lectura por token -----------------------------------------
class StorefrontOrderAddonView(_CamelModel):
    id: uuid.UUID
    name: str
    price: str


class StorefrontOrderLineView(_CamelModel):
    """Una línea con su veredicto propio.

    `refusal` es el motivo por el que no se deja tocar, y `reason` la frase ya escrita. Van
    los dos porque el front decide con el código y pinta con la frase; sin el código tendría
    que comparar textos, y sin la frase enseñaría un código.
    """

    item_id: uuid.UUID
    variant_id: uuid.UUID
    name: str
    quantity: int
    unit_price: str
    line_subtotal: str
    status: str
    addons: list[StorefrontOrderAddonView]
    removed_ingredients: list[str]
    note: str | None
    removable_ingredients: list[str]
    editable: bool
    refusal: str | None = None
    reason: str | None = None

    @classmethod
    def from_line(cls, line: ViewLine) -> StorefrontOrderLineView:
        return cls(
            item_id=line.item_id,
            variant_id=line.variant_id,
            name=line.name,
            quantity=line.quantity,
            unit_price=_money(line.unit_price),
            line_subtotal=_money(line.line_subtotal),
            status=line.status,
            addons=[
                StorefrontOrderAddonView(id=a.id, name=a.name, price=_money(a.price))
                for a in line.addons
            ],
            removed_ingredients=list(line.removed_ingredients),
            note=line.note,
            removable_ingredients=list(line.removable_ingredients),
            editable=line.refusal is None,
            refusal=None if line.refusal is None else str(line.refusal),
            reason=refusal_text(line.refusal),
        )


class StorefrontOrderView(_CamelModel):
    """El pedido detrás del enlace. Nada de otros pedidos, otros clientes u otras sedes."""

    order_id: uuid.UUID
    status: str
    kitchen_state: str
    total: str
    paid: str
    outstanding: str
    editable: bool
    refusal: str | None = None
    reason: str | None = None
    lines: list[StorefrontOrderLineView]
    #: Con quién hablar para lo que esta pantalla no hace. `null` si la sede no tiene teléfono.
    contact_phone: str | None = None
    #: El método que el cliente eligió al pedir. Decide qué se le dice del saldo.
    payment_method: str | None = None
    #: Hay un comprobante esperando a que el restaurante lo confirme. NO significa pagado: el
    #: saldo de arriba sigue siendo el que es hasta que una persona lo verifica.
    payment_proof_pending: bool = False

    @classmethod
    def from_view(cls, view: OrderView) -> StorefrontOrderView:
        assert view.order.id is not None
        return cls(
            order_id=view.order.id,
            status=view.order.status,
            kitchen_state=view.order.kitchen_state,
            total=_money(view.total),
            paid=_money(view.paid),
            outstanding=_money(view.outstanding),
            editable=view.refusal is None,
            refusal=None if view.refusal is None else str(view.refusal),
            reason=refusal_text(view.refusal),
            lines=[StorefrontOrderLineView.from_line(line) for line in view.lines],
            contact_phone=view.contact_phone,
            payment_method=view.payment_method,
            payment_proof_pending=view.payment_proof_pending,
        )


# --- "Mi pedido": edición por token ------------------------------------------
# El catálogo de verbos permitidos ES esta forma: lo que no se puede pedir no tiene campo.
# No hay `remove`, ni cantidad a la baja, ni cancelar — y tampoco hay precio: si llegara uno,
# `extra="ignore"` lo tira antes de que nadie lo lea.
class StorefrontAddLineRequest(_RequestModel):
    variant_id: uuid.UUID = Field(alias="variantId")
    quantity: int = Field(default=1, gt=0)
    addon_ids: list[uuid.UUID] = Field(default_factory=list, alias="addonIds")
    removed_ingredients: list[str] = Field(
        default_factory=list, alias="removedIngredients"
    )
    note: str | None = Field(default=None, max_length=255)


class StorefrontEditLineRequest(_RequestModel):
    item_id: uuid.UUID = Field(alias="itemId")
    #: Sólo hacia arriba. Bajarla se rechaza en el servicio con su propio motivo.
    quantity: int | None = Field(default=None, gt=0)
    add_addon_ids: list[uuid.UUID] = Field(default_factory=list, alias="addAddonIds")
    #: Las exclusiones ELEGIDAS, no la nota montada: el servidor compone el texto.
    removed_ingredients: list[str] | None = Field(
        default=None, alias="removedIngredients"
    )
    note: str | None = Field(default=None, max_length=255)
    #: Cambiar el producto de la línea. Se rechaza si el pedido ya está pagado.
    variant_id: uuid.UUID | None = Field(default=None, alias="variantId")


class StorefrontOrderEditRequest(_RequestModel):
    add: list[StorefrontAddLineRequest] = Field(default_factory=list)
    edit: list[StorefrontEditLineRequest] = Field(default_factory=list)


class StorefrontOrderEditResponse(_CamelModel):
    """Lo que hay que poder decirle al cliente después de editar.

    `totalBefore` va aparte porque el delta a pagar es la única cifra que el cliente no puede
    calcular mirando la pantalla, y es justo la que evita la discusión en la puerta.
    """

    total_before: str
    order: StorefrontOrderView


class StorefrontPaymentProofResponse(_CamelModel):
    """Lo que se le contesta a quien acaba de mandar su comprobante.

    Lleva el pedido entero a propósito: el cliente tiene que ver que su saldo **no cambió**.
    Devolver sólo un "ok" invitaría a leerlo como "ya está pagado".
    """

    claim_id: uuid.UUID
    status: str
    order: StorefrontOrderView
