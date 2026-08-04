"""order_items: optional free-text kitchen note

Revision ID: 0012_order_item_notes
Revises: 2ed5e401d539
Create Date: 2026-07-11 00:00:00.000000

A diner can ask for a plate "sin lechuga, sin queso" — same price, but the cook must
know. Free text (≤255), nullable, set at add time. No price or inventory effect.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012_order_item_notes"
down_revision: str | None = "2ed5e401d539"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("order_items", sa.Column("notes", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("order_items", "notes")
