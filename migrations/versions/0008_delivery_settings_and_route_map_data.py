"""delivery settings (business pin + ring step) and route map data (zones/color/position)

Revision ID: 0008_delivery_map
Revises: 0007_station_task_lists
Create Date: 2026-07-01 00:00:00.000000

The coverage-map slice of the Domicilios screen:
- ``delivery_settings``: one row per branch — business latitude/longitude (nullable until the
  pin is placed) and the uniform ring band width ``ring_step_km``.
- ``delivery_routes``: ``zones`` (JSON string array, backfilled from the free-text
  ``covered_zones`` split on commas), ``color`` (hex, nullable) and ``position`` (ring band
  order, backfilled sequentially per branch). ``covered_zones`` is dropped — ``zones`` becomes
  the single source of truth; downgrade re-serializes it back.
"""
from __future__ import annotations

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008_delivery_map"
down_revision: str | None = "0007_station_task_lists"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "delivery_settings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("latitude", sa.Numeric(10, 7), nullable=True),
        sa.Column("longitude", sa.Numeric(10, 7), nullable=True),
        sa.Column(
            "ring_step_km", sa.Numeric(4, 2), server_default="1.0", nullable=False
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("branch_id", name="uq_delivery_settings_branch"),
    )
    op.create_index(
        op.f("ix_delivery_settings_tenant_id"), "delivery_settings", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_delivery_settings_branch_id"), "delivery_settings", ["branch_id"]
    )

    op.add_column(
        "delivery_routes",
        sa.Column("zones", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "delivery_routes", sa.Column("color", sa.String(length=7), nullable=True)
    )
    op.add_column(
        "delivery_routes",
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
    )

    # Backfill zones from the free-text covered_zones (comma-separated) and position
    # sequentially per branch (deterministic id order — no created_at exists on routes).
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, branch_id, covered_zones FROM delivery_routes "
            "ORDER BY branch_id, id"
        )
    ).fetchall()
    position_by_branch: dict[str, int] = {}
    for route_id, branch_id, covered_zones in rows:
        zones = [z.strip() for z in (covered_zones or "").split(",") if z.strip()]
        position = position_by_branch.get(str(branch_id), 0)
        position_by_branch[str(branch_id)] = position + 1
        bind.execute(
            sa.text(
                "UPDATE delivery_routes SET zones = :zones, position = :position "
                "WHERE id = :id"
            ),
            {"zones": json.dumps(zones), "position": position, "id": route_id},
        )

    op.drop_column("delivery_routes", "covered_zones")


def downgrade() -> None:
    op.add_column(
        "delivery_routes",
        sa.Column("covered_zones", sa.String(length=500), nullable=True),
    )
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT id, zones FROM delivery_routes")).fetchall()
    for route_id, zones in rows:
        parsed = zones if isinstance(zones, list) else json.loads(zones or "[]")
        bind.execute(
            sa.text("UPDATE delivery_routes SET covered_zones = :cz WHERE id = :id"),
            {"cz": ", ".join(parsed) or None, "id": route_id},
        )
    op.drop_column("delivery_routes", "position")
    op.drop_column("delivery_routes", "color")
    op.drop_column("delivery_routes", "zones")
    op.drop_index(
        op.f("ix_delivery_settings_branch_id"), table_name="delivery_settings"
    )
    op.drop_index(
        op.f("ix_delivery_settings_tenant_id"), table_name="delivery_settings"
    )
    op.drop_table("delivery_settings")
