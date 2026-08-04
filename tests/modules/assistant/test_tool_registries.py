"""El registro ES la frontera. Estas pruebas comprueban que lo sea.

No se prueba que el asistente "se niegue" a dar las ventas a un cliente: se prueba que la
herramienta **no exista** en su registro. La diferencia importa — lo primero depende de que
un modelo obedezca un texto, lo segundo no depende de nada.

Los servicios van como dobles vacíos a propósito: aquí no se prueba qué contestan las
herramientas, sino cuáles se construyen y para quién.
"""

from __future__ import annotations

import uuid
from typing import Any, cast

from restaurante.modules.assistant.application.use_cases.tools import (
    build_customer_registry,
    build_employee_registry,
)

#: Todo lo que un cliente NO puede tener. Si alguien añade una herramienta de personal y se
#: le olvida el permiso, esta lista es lo que lo caza.
STAFF_ONLY = {"open_orders", "low_stock", "sales_summary", "top_products"}

ALL_PERMISSIONS = {"menu.read", "orders.read", "inventory.read", "reports.view"}


class _Stub:
    """Un servicio que nadie va a llamar en estas pruebas."""

    def __getattr__(self, name: str) -> Any:  # pragma: no cover - nunca se invoca
        raise AssertionError(f"no debería llamarse: {name}")


def _services() -> dict[str, Any]:
    stub = cast(Any, _Stub())
    return {
        "storefront": stub,
        "business": stub,
        "orders": stub,
        "inventory": stub,
        "reports": stub,
    }


def _names(tools: list[Any]) -> set[str]:
    return {tool.name for tool in tools}


def test_customer_registry_has_no_staff_tools() -> None:
    tools = build_customer_registry(
        tenant_id=uuid.uuid4(),
        branch_id=uuid.uuid4(),
        whatsapp_contact_id=uuid.uuid4(),
        **{
            k: v
            for k, v in _services().items()
            if k in {"storefront", "business", "orders"}
        },
    )
    assert _names(tools) == {"menu", "branch_hours", "my_orders"}
    assert not _names(tools) & STAFF_ONLY


def test_customer_without_known_contact_cannot_ask_for_orders() -> None:
    """Sin contacto no hay `my_orders`: "mis pedidos" exige saber de quién son."""
    tools = build_customer_registry(
        tenant_id=uuid.uuid4(),
        branch_id=uuid.uuid4(),
        whatsapp_contact_id=None,
        **{
            k: v
            for k, v in _services().items()
            if k in {"storefront", "business", "orders"}
        },
    )
    assert "my_orders" not in _names(tools)


def test_employee_registry_matches_permissions() -> None:
    common = {
        "tenant_id": uuid.uuid4(),
        "branch_id": uuid.uuid4(),
        **_services(),
    }

    # Un mesero: ve la carta y los pedidos, no el stock ni las ventas.
    waiter = build_employee_registry(
        permissions={"menu.read", "orders.read"}, **common
    )
    assert _names(waiter) == {"branch_hours", "menu", "open_orders"}
    assert "sales_summary" not in _names(waiter)

    # El dueño: todo.
    owner = build_employee_registry(permissions=ALL_PERMISSIONS, **common)
    assert STAFF_ONLY <= _names(owner)

    # Alguien sin ningún permiso de lectura conserva sólo lo que no es un secreto.
    nobody = build_employee_registry(permissions=set(), **common)
    assert _names(nobody) == {"branch_hours"}


def test_every_staff_tool_is_gated() -> None:
    """Ninguna herramienta de personal puede colarse sin permiso.

    Es la prueba que sobrevive a la siguiente herramienta que alguien añada: si aparece en
    el registro de quien no tiene permisos, falla aquí y no en producción.
    """
    ungated = _names(
        build_employee_registry(
            permissions=set(), tenant_id=uuid.uuid4(), branch_id=uuid.uuid4(), **_services()
        )
    )
    assert not ungated & STAFF_ONLY
