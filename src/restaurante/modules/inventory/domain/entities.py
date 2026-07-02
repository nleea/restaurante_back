"""Framework-free domain entities of the Inventory module.

Plain dataclasses mirroring the ORM tables (including `tenant_id`/`branch_id`).
Required business fields come first; `id` and server-defaulted timestamps are
optional so the application layer can build an entity before persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class InventoryStock:
    """Current on-hand quantity of an ingredient at a branch."""

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    ingredient_id: uuid.UUID
    current_quantity: Decimal = Decimal(0)
    min_stock: Decimal = Decimal(0)
    id: uuid.UUID | None = None
    updated_at: datetime | None = None


@dataclass
class InventoryMovement:
    """Audit log entry of a change applied to an ingredient's stock."""

    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    ingredient_id: uuid.UUID
    type: str
    reason: str
    quantity: Decimal
    employee_id: uuid.UUID
    reference_id: uuid.UUID | None = None
    notes: str | None = None
    id: uuid.UUID | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
