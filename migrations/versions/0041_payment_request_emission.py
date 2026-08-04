"""Emission state for delivery payment requests.

A request is created with its link already sent, or already failed to send: the raw token only
exists inside the creating transaction, so there is no later pass that could try again. These
columns are therefore an operational read model — they tell a dispatcher whether the customer
ever received the link, so they can re-issue a NEW request rather than resend an unrecoverable one.

Revision ID: 0041_payment_request_emission
Revises: 0040_fix_tariff_precision
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0041_payment_request_emission"
down_revision: str | None = "0040_fix_tariff_precision"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # `pending` and not `sent`: the rows that already exist were created before anything could
    # emit them, and claiming they were sent would hide exactly the deliveries a dispatcher
    # needs to chase.
    op.add_column(
        "delivery_payment_requests",
        sa.Column(
            "emission_status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
    )
    op.add_column(
        "delivery_payment_requests",
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "delivery_payment_requests",
        sa.Column("emission_failure_reason", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("delivery_payment_requests", "emission_failure_reason")
    op.drop_column("delivery_payment_requests", "emitted_at")
    op.drop_column("delivery_payment_requests", "emission_status")
