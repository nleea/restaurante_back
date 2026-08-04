"""menu_appearance table + ingredients.is_customer_removable

Revision ID: 0016_menu_appearance
Revises: 0015_run_positions
Create Date: 2026-07-18 00:00:00.000000

Persists the public-carta appearance config as a single JSONB document per tenant
(one row, `tenant_id` UNIQUE) so the admin editor's draft/publish survives reloads
and the future storefront reads the same object the admin writes.

Also adds `ingredients.is_customer_removable` (global per insumo, default true): the
"quitar" list the diner sees is filtered by this flag, so salt/oil-style noise can be
hidden without touching each recipe line. Existing rows backfill to true.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0016_menu_appearance"
down_revision: str | None = "0015_run_positions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "menu_appearance",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_menu_appearance_tenant"),
    )
    op.create_index(
        op.f("ix_menu_appearance_tenant_id"), "menu_appearance", ["tenant_id"]
    )

    op.add_column(
        "ingredients",
        sa.Column(
            "is_customer_removable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("ingredients", "is_customer_removable")
    op.drop_index(op.f("ix_menu_appearance_tenant_id"), table_name="menu_appearance")
    op.drop_table("menu_appearance")
