"""ORM models of the Orders module.

Holds the operational core: `dining_tables`, `orders` (comandas), `order_items`,
`order_item_addons`, `order_payments`, `cancellations` and `receipt_prints`.

Tenancy notes:
- Most tables are branch-scoped (`BranchScopedMixin` => `tenant_id` + `branch_id`)
  since they belong to a concrete branch's operation.
- `order_item_addons` is tenant-scoped only (`TenantScopedMixin`): it is a child
  detail of an order item and inherits the branch through it, so it carries just
  `tenant_id`.

FK targets `customers`, `whatsapp_contacts`, `employees`, `product_variants`,
`addons` and `cash_sessions` live in other modules and are referenced by string.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from restaurante.shared.database import (
    Base,
    BranchScopedMixin,
    TenantScopedMixin,
    TimestampMixin,
)


class DiningTableModel(Base, BranchScopedMixin):
    __tablename__ = "dining_tables"
    __table_args__ = (
        UniqueConstraint("branch_id", "number", name="uq_dining_tables_branch_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(String(20), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="free", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class OrderModel(Base, BranchScopedMixin, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    channel: Mapped[str] = mapped_column(String(20), nullable=False)
    dining_table_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("dining_tables.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    whatsapp_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("whatsapp_contacts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Operating shift: the cash session open at creation. Nullable (pre-boundary rows / SET NULL
    # if the session row is ever removed). Live boards filter on this via the order.
    cash_session_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("cash_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    # Customer's chosen payment method recorded as an INTENT (e.g. a storefront web
    # order). Nullable: it is NOT a received payment — staff register an
    # `order_payments` row when they actually collect, which is what paid/close math reads.
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    discount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    delivery_fee: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), default=0, server_default="0", nullable=False
    )
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    kitchen_state: Mapped[str] = mapped_column(
        String(20), default="none", server_default="none", nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # El enlace con el que el propio cliente edita ESTE pedido. Es una URL-capacidad: quien la
    # tenga, edita — por eso es por pedido y no el token del chat, que identifica al contacto y
    # convertiría un enlace reenviado en acceso a todos sus pedidos.
    #
    # Único global (no por tenant): adivinar uno tiene que ser imposible, no improbable dentro
    # de un negocio. Nace nulo en los pedidos que ya existían, y sin token no hay vista.
    edit_token: Mapped[str | None] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    edit_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OrderItemModel(Base, BranchScopedMixin, TimestampMixin):
    __tablename__ = "order_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_variant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("product_variants.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    line_subtotal: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    # Free-text kitchen note ("sin lechuga"), set at add time. No price/inventory effect.
    notes: Mapped[str | None] = mapped_column(String(255), nullable=True)


class OrderItemAddonModel(Base, TenantScopedMixin):
    __tablename__ = "order_item_addons"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("order_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    addon_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("addons.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    applied_price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)


class OrderPaymentModel(Base, BranchScopedMixin, TimestampMixin):
    __tablename__ = "order_payments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    cash_session_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("cash_sessions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    diner_reference: Mapped[str | None] = mapped_column(String(50), nullable=True)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )


class OrderPaymentClaimModel(Base, BranchScopedMixin, TimestampMixin):
    """Lo que el CLIENTE dice haber pagado, con su comprobante. NO es un pago.

    Tabla propia y no una fila en `order_payments` por una razón concreta: `payments_total`
    suma esa tabla, y de ella cuelgan la verificación de cocina, el cierre, la caja y el
    arqueo. Una declaración ahí —aunque fuera con un `verified = false`— haría que el pedido
    entrara a cocina porque el cliente dijo que pagó, y obligaría a excluir el estado nuevo en
    todas las consultas de dinero del sistema; la primera que se olvidara sería un descuadre.

    Lo que no está en `order_payments` no es dinero en ninguna pantalla. Esa es toda la idea.
    """

    __tablename__ = "order_payment_claims"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Lo que el cliente DICE que pagó. No se compara con nada automáticamente: existe para que
    #: quien mira el comprobante pueda decidir de un vistazo.
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    #: URL pública del comprobante en R2. Nulo si llegó por otra vía (el chat, una llamada).
    proof_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    #: Por qué se rechazó, para poder decírselo al cliente con esas palabras.
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolved_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class OrderRefundModel(Base, BranchScopedMixin, TimestampMixin):
    """Dinero que le debemos al cliente por un pedido prepagado que no se entregó.

    Sólo lo prepagado genera devoluciones: el efectivo se cobra en la puerta, así que un
    pedido no entregado en efectivo nunca se pagó y no hay nada que devolver. Y como lo
    prepagado nunca tocó el cajón, confirmarla crea un movimiento de salida **con el método
    original** — jamás efectivo, o el arqueo esperaría menos plata de la que hay.

    Existe como registro propio, y no derivado, porque es plata saliendo del negocio: "quién
    autorizó esta devolución" es la pregunta que se hace un dueño el día que aparece una que
    nadie recuerda. Derivarla tampoco permitiría decir "esta no se devuelve, se arregló de
    otra forma" sin dejarla colgada para siempre.
    """

    __tablename__ = "order_refunds"
    __table_args__ = (
        # Una por pedido: marcar dos veces no entregada no duplica la deuda.
        UniqueConstraint("order_id", name="uq_order_refunds_order"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # El método por el que ENTRÓ la plata, que es por el que tiene que salir.
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )
    # Quién la resolvió y por qué. Nulos mientras está pendiente.
    resolved_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class CancellationModel(Base, BranchScopedMixin, TimestampMixin):
    __tablename__ = "cancellations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    order_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("order_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    requires_authorization: Mapped[bool] = mapped_column(Boolean, nullable=False)
    requested_by_employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    authorized_by_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="approved", nullable=False)


class ReceiptPrintModel(Base, BranchScopedMixin, TimestampMixin):
    __tablename__ = "receipt_prints"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("employees.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_reprint: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
