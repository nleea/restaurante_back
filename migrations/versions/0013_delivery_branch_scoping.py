"""delivery: branch_id on deliveries, runs and route drivers

Revision ID: 0013_delivery_branch_scoping
Revises: 0012_order_item_notes
Create Date: 2026-07-15 00:00:00.000000

The delivery module was half branch-scoped: routes and settings carried `branch_id`, the
operational records (order_deliveries, delivery_runs, delivery_route_drivers) did not — so a
two-branch tenant's dispatch board would mix both branches' work.

Backfill is deterministic and cannot orphan a row: every source FK is itself NOT NULL.

    order_deliveries.order_id        NOT NULL -> orders.branch_id          NOT NULL
    delivery_runs.delivery_route_id  NOT NULL -> delivery_routes.branch_id NOT NULL
    delivery_route_drivers.route_id  NOT NULL -> delivery_routes.branch_id NOT NULL

Hence add-nullable -> backfill -> set NOT NULL, rather than a bare NOT NULL add.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013_delivery_branch_scoping"
down_revision: str | None = "0012_order_item_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# table -> (parent table, local FK column, parent PK column)
_BACKFILL: tuple[tuple[str, str, str, str], ...] = (
    ("order_deliveries", "orders", "order_id", "id"),
    ("delivery_runs", "delivery_routes", "delivery_route_id", "id"),
    ("delivery_route_drivers", "delivery_routes", "delivery_route_id", "id"),
)


def upgrade() -> None:
    for table, parent, fk_column, parent_pk in _BACKFILL:
        # 1. nullable, so existing rows survive the add
        op.add_column(table, sa.Column("branch_id", sa.Uuid(), nullable=True))

        # 2. derive each row's branch from its parent
        op.execute(
            sa.text(
                f"UPDATE {table} SET branch_id = ("  # noqa: S608 - fixed identifiers above
                f"SELECT p.branch_id FROM {parent} AS p "
                f"WHERE p.{parent_pk} = {table}.{fk_column})"
            )
        )

        # 3. now that every row has one, hold the invariant
        op.alter_column(table, "branch_id", existing_type=sa.Uuid(), nullable=False)

        op.create_index(
            op.f(f"ix_{table}_branch_id"), table, ["branch_id"], unique=False
        )
        op.create_foreign_key(
            op.f(f"fk_{table}_branch_id_branches"),
            table,
            "branches",
            ["branch_id"],
            ["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    # The derivation is recomputable from the same FKs, so dropping loses no information.
    for table, _parent, _fk_column, _parent_pk in reversed(_BACKFILL):
        op.drop_constraint(
            op.f(f"fk_{table}_branch_id_branches"), table, type_="foreignkey"
        )
        op.drop_index(op.f(f"ix_{table}_branch_id"), table_name=table)
        op.drop_column(table, "branch_id")
