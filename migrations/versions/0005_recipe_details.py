"""recipe details (preparation steps + allergens) per product variant

Revision ID: 0005_recipe_details
Revises: 0004_kitchen_roles_rollup
Create Date: 2026-07-01 00:00:00.000000

Additive: new ``recipe_details`` table (at most one row per product variant) feeding the
KDS recipe drawer — ordered preparation ``steps`` and closed-vocabulary ``allergens`` as
JSON string arrays, plus an optional ``photo_label``.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0005_recipe_details"
down_revision: str | None = "0004_kitchen_roles_rollup"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "recipe_details",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("product_variant_id", sa.Uuid(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("allergens", sa.JSON(), nullable=False),
        sa.Column("photo_label", sa.String(length=150), nullable=True),
        sa.ForeignKeyConstraint(
            ["product_variant_id"], ["product_variants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_variant_id", name="uq_recipe_details_variant"),
    )
    op.create_index(
        op.f("ix_recipe_details_product_variant_id"),
        "recipe_details",
        ["product_variant_id"],
    )
    op.create_index(
        op.f("ix_recipe_details_tenant_id"), "recipe_details", ["tenant_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_recipe_details_tenant_id"), table_name="recipe_details")
    op.drop_index(
        op.f("ix_recipe_details_product_variant_id"), table_name="recipe_details"
    )
    op.drop_table("recipe_details")
