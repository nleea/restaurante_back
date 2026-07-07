"""shift scheduling: templates, shift status/coverage, time-off requests

Revision ID: 0011_shift_scheduling
Revises: 0010_ingredient_category
Create Date: 2026-07-05 00:00:00.000000

Recurring `shift_templates` author materialized `planned_shifts`; the shift gains
status/origin/coverage so day-off and coverage are state on the row (not a side
table); `time_off_requests` drive the approve/reject loop. Existing planned
shifts backfill to status='scheduled', origin='manual' via server defaults.
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011_shift_scheduling"
down_revision: str | None = "0010_ingredient_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shift_templates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.Uuid(),
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            sa.Uuid(),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("weekdays", sa.JSON(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("generated_through", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_shift_templates_tenant_id", "shift_templates", ["tenant_id"])
    op.create_index("ix_shift_templates_branch_id", "shift_templates", ["branch_id"])

    op.create_table(
        "time_off_requests",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "branch_id",
            sa.Uuid(),
            sa.ForeignKey("branches.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "employee_id",
            sa.Uuid(),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("request_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("decided_by", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_time_off_requests_tenant_id", "time_off_requests", ["tenant_id"])
    op.create_index("ix_time_off_requests_branch_id", "time_off_requests", ["branch_id"])
    op.create_index(
        "ix_time_off_requests_employee_id", "time_off_requests", ["employee_id"]
    )

    op.add_column(
        "planned_shifts",
        sa.Column("status", sa.String(length=16), server_default="scheduled", nullable=False),
    )
    op.add_column(
        "planned_shifts",
        sa.Column("origin", sa.String(length=16), server_default="manual", nullable=False),
    )
    op.add_column(
        "planned_shifts",
        sa.Column(
            "covered_by_employee_id",
            sa.Uuid(),
            sa.ForeignKey("employees.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("planned_shifts", sa.Column("note", sa.String(length=200), nullable=True))
    op.create_index(
        "ix_planned_shifts_covered_by_employee_id",
        "planned_shifts",
        ["covered_by_employee_id"],
    )
    op.create_unique_constraint(
        "uq_planned_shift_slot",
        "planned_shifts",
        ["tenant_id", "employee_id", "shift_date"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_planned_shift_slot", "planned_shifts", type_="unique")
    op.drop_index("ix_planned_shifts_covered_by_employee_id", "planned_shifts")
    op.drop_column("planned_shifts", "note")
    op.drop_column("planned_shifts", "covered_by_employee_id")
    op.drop_column("planned_shifts", "origin")
    op.drop_column("planned_shifts", "status")
    op.drop_table("time_off_requests")
    op.drop_table("shift_templates")
