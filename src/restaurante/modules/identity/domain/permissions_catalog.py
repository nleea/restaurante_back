"""Static catalog of system permissions and the base (global) roles.

This is the source of truth the seed uses to populate `permissions`, `roles` and
`role_permissions`. Permission codes are `<module>.<action>` in English.

Keeping it in the domain layer (framework-free) lets both the seed and the tests
build a coherent RBAC baseline without duplicating literals.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionDef:
    code: str
    name: str
    module: str
    description: str


# --- Permission catalog -----------------------------------------------------
def _p(code: str, name: str, module: str, description: str) -> PermissionDef:
    return PermissionDef(code, name, module, description)


PERMISSIONS: tuple[PermissionDef, ...] = (
    # Access control / identity
    _p("rbac.manage", "Manage roles and permissions", "identity",
       "Create roles, assign permissions and manage user access."),
    _p("users.read", "View users", "identity", "List and view users."),
    _p("users.manage", "Manage users", "identity", "Create and edit users."),
    # Menu / products
    _p("menu.read", "View menu", "menu", "View products, prices and variants."),
    _p("menu.manage", "Manage menu", "menu",
       "Create and edit products, prices, variants and addons."),
    # Orders
    _p("orders.read", "View orders", "orders", "View orders and items."),
    _p("orders.create", "Create orders", "orders", "Open orders and add items."),
    _p("orders.update", "Update orders", "orders", "Modify open orders."),
    _p("orders.cancel", "Cancel orders", "orders", "Cancel orders or items (void)."),
    _p("orders.pay", "Charge orders", "orders", "Register order payments."),
    # Inventory
    _p("inventory.read", "View inventory", "inventory", "View stock and movements."),
    _p("inventory.adjust", "Adjust inventory", "inventory",
       "Register inventory movements/adjustments."),
    # Recipes / BOM
    _p("recipes.read", "View recipes", "recipes",
       "View ingredients and product recipes (BOM)."),
    _p("recipes.manage", "Manage recipes", "recipes",
       "Manage ingredients and product recipes (BOM)."),
    # Purchasing
    _p("purchasing.read", "View purchasing", "purchasing",
       "View suppliers, requests and orders."),
    _p("purchasing.manage", "Manage purchasing", "purchasing",
       "Create suppliers, requests and purchase orders."),
    _p("purchasing.approve", "Approve purchases", "purchasing",
       "Approve purchase requests."),
    # Cash
    _p("cash.read", "View cash", "cash", "View cash sessions and movements."),
    _p("cash.open", "Open cash", "cash", "Open a cash session."),
    _p("cash.close", "Close cash", "cash", "Close a cash session."),
    _p("cash.move", "Move cash", "cash", "Register cash movements."),
    # Finance
    _p("finance.read", "View finance", "finance", "View expenses and credits."),
    _p("finance.manage", "Manage finance", "finance",
       "Register expenses and manage credits."),
    # Staff
    _p("staff.read", "View staff", "staff", "View employees, shifts and attendance."),
    _p("staff.manage", "Manage staff", "staff",
       "Manage employees, shifts and attendance."),
    # Customers
    _p("customers.read", "View customers", "customers",
       "View customers and preferences."),
    _p("customers.manage", "Manage customers", "customers",
       "Create and edit customers."),
    # Kitchen (KDS)
    _p("kitchen.read", "View kitchen", "kitchen", "View kitchen stations and tickets."),
    _p("kitchen.update", "Update kitchen", "kitchen",
       "Advance ticket states in the KDS."),
    # Delivery
    _p("delivery.read", "View delivery", "delivery", "View routes and deliveries."),
    _p("delivery.assign", "Assign delivery", "delivery",
       "Assign drivers and routes to deliveries."),
    _p("delivery.manage", "Manage delivery", "delivery",
       "Manage routes, drivers and runs."),
    # Messaging (WhatsApp)
    _p("messaging.read", "View messaging", "messaging",
       "View WhatsApp conversations."),
    _p("messaging.send", "Send messages", "messaging",
       "Send WhatsApp messages / take over chats."),
    # Catalog (global reference data)
    _p("catalog.read", "View catalog", "catalog",
       "View countries, cities and units of measure."),
    _p("catalog.manage", "Manage catalog", "catalog",
       "Manage countries, cities and units of measure."),
    # Audit (cross-cutting log)
    _p("audit.read", "View audit log", "audit",
       "Query the cross-cutting audit log."),
    # Reports
    _p("reports.view", "View reports", "reports", "View dashboards and reports."),
)

ALL_PERMISSION_CODES: frozenset[str] = frozenset(p.code for p in PERMISSIONS)


# --- Base (global) roles ----------------------------------------------------
# Each entry maps a base role name to its set of permission codes. `admin` gets
# every permission. These roles are seeded as global (tenant_id NULL, is_global).
BASE_ROLES: dict[str, set[str]] = {
    "admin": set(ALL_PERMISSION_CODES),
    "manager": {
        "users.read", "menu.read", "menu.manage",
        "orders.read", "orders.create", "orders.update", "orders.cancel", "orders.pay",
        "inventory.read", "inventory.adjust",
        "purchasing.read", "purchasing.manage", "purchasing.approve",
        "cash.read", "cash.open", "cash.close", "cash.move",
        "finance.read", "finance.manage",
        "staff.read", "staff.manage",
        "customers.read", "customers.manage",
        "kitchen.read", "delivery.read", "delivery.assign", "delivery.manage",
        "messaging.read", "messaging.send", "reports.view",
    },
    "cashier": {
        "menu.read",
        "orders.read", "orders.create", "orders.update", "orders.pay",
        "cash.read", "cash.open", "cash.close", "cash.move",
        "customers.read", "customers.manage",
    },
    "waiter": {
        "menu.read",
        "orders.read", "orders.create", "orders.update",
        "customers.read",
    },
    "kitchen": {
        "orders.read", "kitchen.read", "kitchen.update",
    },
    "courier": {
        "orders.read", "delivery.read", "messaging.read",
    },
}

ADMIN_ROLE_NAME = "admin"
