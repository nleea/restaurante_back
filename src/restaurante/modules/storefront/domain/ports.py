"""Ports (interfaces) of the Storefront module."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Protocol

from restaurante.modules.storefront.domain.entities import (
    StoreBranch,
    StoreMenu,
    StoreVariant,
)


class DeliveryReadiness(Protocol):
    """Puerto de salida: ¿puede esta sede ponerle precio a un domicilio?

    Existe porque el fallo que evita es SILENCIOSO. Sin bandas de tarifa la cadena entera corre
    igual —el pedido se acepta, se agradece, el worker lo recoge, no encuentra con qué cotizarlo
    y lo marca no cotizable— y el cliente se queda esperando un enlace que no va a llegar. Desde
    fuera se ve como un restaurante que funciona y va lento.

    Puerto y no un import de `delivery` por lo de siempre: la carta pública tiene que poder
    servir sin el módulo de domicilios montado. Sin adaptador enchufado se acepta todo, que es
    exactamente el comportamiento anterior.
    """

    async def can_take_deliveries(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> bool: ...


class StorefrontRepository(Protocol):
    async def link_order_contact(
        self, tenant_id: uuid.UUID, order_id: uuid.UUID, contact_id: uuid.UUID
    ) -> None:
        """Ata el pedido al contacto de WhatsApp que trajo el enlace.

        Es lo que hace que los avisos de estado lleguen sin adivinar por teléfono: el
        pedido sabe exactamente a qué chat le habla.
        """
        ...

    async def get_primary_branch_id(self, tenant_id: uuid.UUID) -> uuid.UUID | None:
        """The tenant's primary active branch (falls back to any active branch)."""
        ...

    async def get_branch_id_by_code(
        self, tenant_id: uuid.UUID, code: str
    ) -> uuid.UUID | None:
        """The ACTIVE branch with that `code`, or ``None``.

        ``None`` must become a 404 upstream, never a fallback to the primary branch:
        the customer believing they ordered from one branch while the ticket prints in
        another is the failure this lookup exists to prevent.
        """
        ...

    async def list_active_branches(
        self, tenant_id: uuid.UUID
    ) -> list[StoreBranch]:
        """Active branches for the public picker (primary first, then by name)."""
        ...

    async def resolve_system_employee(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> uuid.UUID:
        """Find-or-create the per-tenant "Pedidos web" system employee; return its id.

        Web orders have no logged-in user, but ``orders.employee_id`` is NOT NULL — this
        lazily provisions (person + login user + role + employee) once and reuses it after.
        """
        ...

    async def build_menu(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> StoreMenu:
        """Assemble the customer-safe menu read-model for the given branch."""
        ...

    async def sellable_variant_product(
        self, tenant_id: uuid.UUID, variant_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Product id of a sellable variant (active + has a recipe); ``None`` otherwise."""
        ...

    async def product_price(
        self, tenant_id: uuid.UUID, product_id: uuid.UUID, branch_id: uuid.UUID
    ) -> Decimal | None:
        """Active primary-branch price of a product, or ``None`` when unpriced."""
        ...

    async def addon_price(
        self, tenant_id: uuid.UUID, addon_id: uuid.UUID
    ) -> Decimal | None:
        """Price of an active addon, or ``None`` when it does not exist / is inactive."""
        ...

    # --- Describir lo que YA está en un pedido -----------------------------
    async def describe_variants(
        self, tenant_id: uuid.UUID, variant_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, StoreVariant]:
        """Nombre y exclusiones posibles de cada variante pedida, para pintar el pedido.

        Sin filtro de "activa": describe lo que se pidió, no lo que se vende hoy.
        """
        ...

    async def addon_names(
        self, tenant_id: uuid.UUID, addon_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, str]:
        """Nombre de cada adición ya aplicada. El precio lo guarda la propia línea."""
        ...

    async def branch_phone(
        self, tenant_id: uuid.UUID, branch_id: uuid.UUID
    ) -> str | None:
        """El teléfono público de la sede, o `None`.

        Existe para lo que esta vista NO deja hacer: quitar, bajar y cancelar los resuelve una
        persona, y decirlo sin dar cómo alcanzarla es dejar al cliente en el mismo sitio.
        """
        ...
