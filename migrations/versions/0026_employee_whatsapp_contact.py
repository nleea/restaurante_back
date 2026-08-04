"""employees.whatsapp_contact_id — a qué chat se le escribe, elegido a mano

Revision ID: 0026_employee_whatsapp_contact
Revises: 0025_employee_alert_subscription
Create Date: 2026-07-30 00:00:00.000000

Emparejar al empleado con su chat por TELÉFONO no funciona, y no es un detalle a pulir: es
imposible por diseño de WhatsApp.

Cuando WhatsApp está en modo privacidad manda un `@lid` —`196125537607835@lid`— en vez del
número. Ese identificador es lo único con lo que se le puede escribir a esa persona, y **de
esos contactos nunca sabemos el teléfono**. Así que un teléfono tecleado en Personal no puede
coincidir con nada, por mucho que la persona escriba al negocio.

La única señal fiable de "a esta persona se le puede escribir" es que YA ESCRIBIÓ. Así que en
vez de deducirlo, se elige: el dueño empareja al empleado con uno de los chats que ya
existen. Eso resuelve de una vez el `@lid`, el formato del número y el indicativo del país.

`ON DELETE SET NULL`: si el contacto desaparece, el empleado sigue existiendo — simplemente
deja de tener a dónde escribirle, que es la verdad.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0026_employee_whatsapp_contact"
down_revision: str | None = "0025_employee_alert_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employees", sa.Column("whatsapp_contact_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_employees_whatsapp_contact",
        "employees",
        "whatsapp_contacts",
        ["whatsapp_contact_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_employees_whatsapp_contact", "employees", type_="foreignkey")
    op.drop_column("employees", "whatsapp_contact_id")
