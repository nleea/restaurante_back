"""El colchón del stock bajo pasa a ser un PORCENTAJE del mínimo

Revision ID: 0035_low_stock_buffer_percent
Revises: 0034_whatsapp_quick_replies
Create Date: 2026-08-01 00:00:00.000000

`alert_rules.recovery_buffer` no cambia de tipo ni de nombre: cambia lo que **significa**, y sólo
para `low_stock`. Antes era una cantidad ("1"); ahora es un porcentaje del mínimo del insumo
("10" = 10%).

El motivo está en el sujeto de esa regla: es el insumo, y cada insumo lleva su propia
`unit_of_measure_id`. Un colchón fijo de 1 pedía un kilo entero de más sobre un mínimo de 2 kg de
camarón (un 50%) y un solo gramo sobre 500 g de sal (un 0,2%). No hay ningún número absoluto que
sea correcto para los dos, así que nadie podía configurarlo bien.

**Los valores actuales se normalizan a 10, no se convierten.** Un "1" que significaba "una unidad
de algo" no tiene traducción honesta a un porcentaje: dependería del mínimo de cada insumo, y la
regla es por sucursal, no por insumo. Cualquier fórmula de conversión inventaría una precisión que
el dato no tiene — y nadie pudo configurarlo con intención, porque no había forma de saber qué
significaba.

**Sólo se tocan las filas de `low_stock`.** Las otras dos reglas leen esta misma columna en su
propia unidad —minutos en la caja abierta, puntos porcentuales en la cuota del asistente— y ahí el
número sí significaba algo. Tocarlas les cambiaría el comportamiento sin motivo.

**Revertir no es gratis**, y es el único punto de este change donde no lo es: el `downgrade`
devuelve el `server_default` pero deja los valores en 10, que como cantidad absoluta es un colchón
enorme. Si se revierte el código, hay que devolver también estos datos a mano.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0035_low_stock_buffer_percent"
down_revision: str | None = "0034_whatsapp_quick_replies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LOW_STOCK = "low_stock"
_PERCENT_DEFAULT = "10"
_ABSOLUTE_DEFAULT = "1"


def upgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE alert_rules SET recovery_buffer = :value WHERE rule_key = :rule"
        ).bindparams(value=10.0, rule=_LOW_STOCK)
    )
    op.alter_column(
        "alert_rules",
        "recovery_buffer",
        existing_type=sa.Float(),
        existing_nullable=False,
        server_default=sa.text(_PERCENT_DEFAULT),
    )


def downgrade() -> None:
    # No se devuelven los valores: ver el docstring. Volver a poner "1" en todas las filas sería
    # inventarse que ése era su valor anterior, y para muchas no lo era.
    op.alter_column(
        "alert_rules",
        "recovery_buffer",
        existing_type=sa.Float(),
        existing_nullable=False,
        server_default=sa.text(_ABSOLUTE_DEFAULT),
    )
