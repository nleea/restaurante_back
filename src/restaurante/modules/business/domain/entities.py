"""Domain entities of the Business module (framework-free dataclasses)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class OperatingHours:
    """One open window for a branch: a weekday + open/close minutes-from-midnight.

    ``close_minute <= open_minute`` means the window crosses midnight (see domain.hours).
    """

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    weekday: int
    open_minute: int
    close_minute: int
    id: uuid.UUID | None = None


@dataclass
class BranchProfile:
    """Per-branch details surfaced in the business profile."""

    id: uuid.UUID
    name: str
    address: str | None
    phone: str | None
    is_primary: bool
    hours: list[OperatingHours] = field(default_factory=list)


@dataclass
class BranchDetailsUpdate:
    """Editable per-branch fields in a profile update.

    `name` es editable porque es lo que el cliente ve: el saludo de WhatsApp y la carta
    pública lo interpolan. Nace como "Main Branch" en la semilla, y sin este campo el único
    modo de arreglarlo era tocar la base de datos. `None` deja el nombre como estaba.
    """

    id: uuid.UUID
    address: str | None
    phone: str | None
    name: str | None = None


@dataclass
class BusinessProfile:
    """The consolidated read: tenant identity + branches + a staff-roster reference.

    Name/photo are the single identity source. This aggregates existing tenant/branch
    data plus structured hours; it does not duplicate them into a new table.
    """

    tenant_id: uuid.UUID
    name: str
    tax_id: str | None
    email: str | None
    phone: str | None
    photo_url: str | None
    banner_url: str | None
    #: QR de pago del negocio (Nequi/Bancolombia). Uno solo: la cuenta a la que se transfiere
    #: es del negocio, no de cada sede. Vive donde el logo —en la apariencia— para no inventar
    #: una segunda fuente de las imágenes del negocio.
    payment_qr_url: str | None = None
    branches: list[BranchProfile] = field(default_factory=list)
    staff_count: int = 0
