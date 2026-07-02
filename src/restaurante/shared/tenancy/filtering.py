"""Filtro automático de tenancy (defensa en profundidad).

Aplica `tenant_id == <tenant actual>` a TODA operación ORM (SELECT, y también
UPDATE/DELETE masivos) sobre entidades que heredan de `TenantScopedMixin`. Esto
evita fugas o sobre-escrituras de datos entre tenants si en algún repositorio se
olvida el filtro explícito.

Para casos legítimos que deban saltarse el filtro (p.ej. tareas administrativas
o el propio middleware que resuelve el tenant), pasar
`execution_options(skip_tenant_filter=True)` a la consulta.
"""

from __future__ import annotations

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from restaurante.shared.database import TenantScopedMixin
from restaurante.shared.tenancy.context import get_current_tenant_id

_installed = False


def install_tenant_filter() -> None:
    """Registra el listener `do_orm_execute` una sola vez (idempotente)."""
    global _installed
    if _installed:
        return

    @event.listens_for(Session, "do_orm_execute")
    def _apply_tenant_filter(state: ORMExecuteState) -> None:
        # Cargas perezosas de columnas/relaciones ya viajan acotadas por el padre.
        if state.is_column_load or state.is_relationship_load:
            return
        # Sólo operaciones que leen o mutan filas de entidades (no DDL, no plain SQL).
        if not (state.is_select or state.is_update or state.is_delete):
            return
        if state.execution_options.get("skip_tenant_filter", False):
            return

        tenant_id = get_current_tenant_id()
        if tenant_id is None:
            return

        state.statement = state.statement.options(
            with_loader_criteria(
                TenantScopedMixin,
                lambda cls: cls.tenant_id == tenant_id,
                include_aliases=True,
            )
        )

    _installed = True
