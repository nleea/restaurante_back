"""guest_profiles: anonymous cookie-identified customer contact data

Revision ID: 0018_guest_profile
Revises: 0017_order_payment_method
Create Date: 2026-07-20 00:00:00.000000

Adds the tenant-scoped `guest_profiles` table backing the storefront guest
profile: a returning anonymous customer (no account) is recognised by an opaque
UUID `token` carried in the `guest_token` cookie, so their name/address/phone
pre-fill checkout. `user_id` is nullable and links the profile to a real user
once the guest logs in (the `claim` flow). The token is unique + indexed; the
cookie never carries personal data, only the token.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0018_guest_profile"
down_revision: str | None = "0017_order_payment_method"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "guest_profiles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("token", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("address", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_guest_profiles_tenant_id"), "guest_profiles", ["tenant_id"]
    )
    op.create_index(
        op.f("ix_guest_profiles_token"), "guest_profiles", ["token"], unique=True
    )
    op.create_index(
        op.f("ix_guest_profiles_user_id"), "guest_profiles", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_guest_profiles_user_id"), table_name="guest_profiles")
    op.drop_index(op.f("ix_guest_profiles_token"), table_name="guest_profiles")
    op.drop_index(op.f("ix_guest_profiles_tenant_id"), table_name="guest_profiles")
    op.drop_table("guest_profiles")
