"""Resolve deliveries abandoned by a cancelled order.

Cancelling an order used to free its table and forget its delivery. Those rows stayed `pending`
with a dead order behind them: they could never reach the kitchen — the order is gone — and they
blocked their shift's cash session with no honest way out, since the only escape was to claim the
delivery failed.

The code no longer creates them. This clears the ones already there.

Deliberately narrow: order `cancelled` AND delivery `pending` AND `delivered_at IS NULL`, all
three at once. Anything that reached a real outcome is untouched, and `delivered_at IS NULL` is
the guarantee that nobody ever resolved it.

Revision ID: 0042_release_orphan_deliveries
Revises: 0041_payment_request_emission
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0042_release_orphan_deliveries"
down_revision: str | None = "0041_payment_request_emission"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `delivered_at` se sella con el mismo gesto: es un desenlace, no un limbo nuevo, y sin él
    # las pantallas que ordenan por fecha de resolución dejarían estas filas al principio para
    # siempre.
    op.execute(
        """
        UPDATE order_deliveries AS d
           SET delivery_status = 'cancelled',
               delivered_at    = now()
          FROM orders AS o
         WHERE o.id = d.order_id
           AND o.status = 'cancelled'
           AND d.delivery_status = 'pending'
           AND d.delivered_at IS NULL
        """
    )


def downgrade() -> None:
    """No revive nada, a propósito.

    Devolver estas filas a `pending` reintroduciría exactamente el bloqueo que la migración
    quitó: entregas sin desenlace posible trabando el cierre de caja de turnos ya pasados. Un
    rollback del código las deja en un estado que los lectores viejos no conocen y vuelven a
    contar como sin resolver — que es el estado anterior, no uno peor.
    """
