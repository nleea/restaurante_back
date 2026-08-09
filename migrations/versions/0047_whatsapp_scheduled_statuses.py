"""Estados de WhatsApp programados: componer una tarjeta y publicarla a una hora.

Es la primera emisión del módulo que **no es una respuesta**, y no rompe la invariante de no
escribir primero porque un estado no aterriza en ninguna conversación: sale en "Novedades", lo abre
quien quiere y caduca solo a las 24 horas.

Tres tablas y una columna, y la forma de las tres sale de decisiones que conviene no deshacer:

`whatsapp_statuses` — la tarjeta. `bg_color` y `font` existen porque el proveedor los EXIGE para un
estado de texto (400 sin ellos), y por eso se validan al guardar: un estado lo publica un worker a
una hora programada sin nadie mirando. **No hay columna `kind`**: las franjas son el horario, y
"todos los días" son siete filas. Un `kind` sería un segundo sitio decidiendo el mismo hecho,
capaz de contradecir a sus propias filas.

`whatsapp_status_slots` — una fila por ocasión, copiando `operating_hours`: minutos desde medianoche
en hora LOCAL de la sede, `weekday` 0=lunes…6=domingo. El CHECK de exclusión mutua (día O fecha,
nunca las dos) vive aquí y no sólo en el dominio porque una inserción de un script no pasa por
`validate_slots`, y una franja ambigua la resolvería el barrido en silencio.

`whatsapp_status_publications` — qué pasó cuando venció una franja, y la única respuesta a "¿se
publicó?". No guarda lo que llegó, porque eso es incognoscible: el proveedor no devuelve vistas y
devuelve 201 aunque la mitad de las tandas se hayan caído dentro de un `Promise.allSettled`. De ahí
`addressed_count` —"a cuántos se dirigió"— y no `recipient_count`, que se lee como "a cuántos llegó"
y es el primer paso hacia una pantalla que dice "visto por 200". Cuatro columnas de exclusión y no
una suma: un total no puede decir *por qué* la audiencia bajó de 340 a 200, y `excluded_by_cap > 0`
es lo único que distingue "llegó a todos los que podía" de "esto se truncó".

`whatsapp_contacts.status_opt_out` — "no me manden más". Va en el contacto y no en la conversación
porque la petición se le hace al negocio; obligar a repetirla en cada sede es cómo se consigue que
la persona bloquee el número. Nace `false` para todos, así que **nadie estrena comportamiento**: sin
estados creados el barrido no encuentra nada y el sistema se comporta igual que antes.

Revision ID: 0047_whatsapp_scheduled_statuses
Revises: 0046_table_bills
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0047_whatsapp_scheduled_statuses"
down_revision: str | None = "0046_table_bills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "whatsapp_statuses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("bg_color", sa.String(length=20), nullable=True),
        sa.Column("font", sa.Integer(), nullable=True),
        sa.Column("caption", sa.String(length=500), nullable=True),
        sa.Column("media_url", sa.String(length=512), nullable=True),
        sa.Column(
            "active", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        # RESTRICT, que es lo que declara `BranchScopedMixin`. 0046 escribió CASCADE aquí y por eso
        # `alembic check` ya venía marcando desfase en `table_bills`; no se hereda el error.
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["employees.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_whatsapp_statuses_tenant_id", "whatsapp_statuses", ["tenant_id"])
    op.create_index("ix_whatsapp_statuses_branch_id", "whatsapp_statuses", ["branch_id"])
    op.create_index(
        "ix_whatsapp_statuses_created_by", "whatsapp_statuses", ["created_by"]
    )

    op.create_table(
        "whatsapp_status_slots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("whatsapp_status_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("on_date", sa.Date(), nullable=True),
        sa.Column("minute", sa.Integer(), nullable=False),
        # Día de la semana O fecha concreta, nunca las dos ni ninguna. En la base y no sólo en el
        # dominio: un script de datos no pasa por `validate_slots`.
        sa.CheckConstraint(
            "(weekday IS NULL) <> (on_date IS NULL)",
            name="ck_whatsapp_status_slots_weekday_xor_date",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        # RESTRICT, que es lo que declara `BranchScopedMixin`. 0046 escribió CASCADE aquí y por eso
        # `alembic check` ya venía marcando desfase en `table_bills`; no se hereda el error.
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["whatsapp_status_id"], ["whatsapp_statuses.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_whatsapp_status_slots_tenant_id", "whatsapp_status_slots", ["tenant_id"]
    )
    op.create_index(
        "ix_whatsapp_status_slots_branch_id", "whatsapp_status_slots", ["branch_id"]
    )
    op.create_index(
        "ix_whatsapp_status_slots_status",
        "whatsapp_status_slots",
        ["whatsapp_status_id"],
    )

    op.create_table(
        "whatsapp_status_publications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("branch_id", sa.Uuid(), nullable=False),
        sa.Column("whatsapp_status_id", sa.Uuid(), nullable=False),
        sa.Column("fired_for_date", sa.Date(), nullable=False),
        sa.Column("minute", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column(
            "addressed_count", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "excluded_no_number", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "excluded_opted_out", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column(
            "excluded_inactive", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("excluded_by_cap", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "late_by_minutes", sa.Integer(), server_default="0", nullable=False
        ),
        sa.Column("provider_message_id", sa.String(length=180), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        # RESTRICT, que es lo que declara `BranchScopedMixin`. 0046 escribió CASCADE aquí y por eso
        # `alembic check` ya venía marcando desfase en `table_bills`; no se hereda el error.
        sa.ForeignKeyConstraint(["branch_id"], ["branches.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["whatsapp_status_id"], ["whatsapp_statuses.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_whatsapp_status_publications_tenant_id",
        "whatsapp_status_publications",
        ["tenant_id"],
    )
    op.create_index(
        "ix_whatsapp_status_publications_branch_id",
        "whatsapp_status_publications",
        ["branch_id"],
    )
    op.create_index(
        "ix_whatsapp_status_publications_status_day",
        "whatsapp_status_publications",
        ["whatsapp_status_id", "fired_for_date"],
    )

    # `false` para todos los contactos existentes: nadie estrena comportamiento.
    op.add_column(
        "whatsapp_contacts",
        sa.Column(
            "status_opt_out",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("whatsapp_contacts", "status_opt_out")
    for name in (
        "ix_whatsapp_status_publications_status_day",
        "ix_whatsapp_status_publications_branch_id",
        "ix_whatsapp_status_publications_tenant_id",
    ):
        op.drop_index(name, table_name="whatsapp_status_publications")
    op.drop_table("whatsapp_status_publications")
    for name in (
        "ix_whatsapp_status_slots_status",
        "ix_whatsapp_status_slots_branch_id",
        "ix_whatsapp_status_slots_tenant_id",
    ):
        op.drop_index(name, table_name="whatsapp_status_slots")
    op.drop_table("whatsapp_status_slots")
    for name in (
        "ix_whatsapp_statuses_created_by",
        "ix_whatsapp_statuses_branch_id",
        "ix_whatsapp_statuses_tenant_id",
    ):
        op.drop_index(name, table_name="whatsapp_statuses")
    op.drop_table("whatsapp_statuses")
