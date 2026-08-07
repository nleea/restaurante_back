"""Framework-free domain entities for the Cash module."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass
class CashSession:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    opened_by_employee_id: uuid.UUID
    opening_amount: Decimal
    status: str = "open"
    id: uuid.UUID | None = None
    opened_at: datetime | None = None
    closed_by_employee_id: uuid.UUID | None = None
    counted_amount: Decimal | None = None
    expected_amount: Decimal | None = None
    difference: Decimal | None = None
    closed_at: datetime | None = None
    notes: str | None = None
    incident: bool = False
    incident_note: str | None = None


@dataclass
class CashMovement:
    tenant_id: uuid.UUID
    branch_id: uuid.UUID
    cash_session_id: uuid.UUID
    type: str
    concept: str
    amount: Decimal
    method: str
    id: uuid.UUID | None = None
    reference_id: uuid.UUID | None = None
    # La cuenta de mesa que produjo este movimiento, cuando la hubo. NO es una columna: se
    # deriva del pedido al que apunta `reference_id`. Existe para que el feed del cajero pueda
    # decir que tres líneas fueron UN solo cobro — cobrar la mesa 5 con un billete deja un
    # movimiento por comanda, y sin esto el cajero ve tres cobros donde hizo uno.
    table_bill_id: uuid.UUID | None = None
    category: str = "other"
    created_at: datetime | None = None
