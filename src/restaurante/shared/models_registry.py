"""Single import point that registers every ORM model on `Base.metadata`.

Importing this module guarantees that all tables (and their cross-module foreign
keys) are known to SQLAlchemy. Use it wherever the full schema must be present:
Alembic autogenerate (`migrations/env.py`) and the test bootstrap
(`Base.metadata.create_all`).

It only triggers import side effects, so the symbols are intentionally unused.
"""

from __future__ import annotations

from restaurante.modules.cash.infrastructure import models as _cash  # noqa: F401
from restaurante.modules.catalog.infrastructure import models as _catalog  # noqa: F401
from restaurante.modules.customers.infrastructure import models as _customers  # noqa: F401
from restaurante.modules.delivery.infrastructure import models as _delivery  # noqa: F401
from restaurante.modules.finance.infrastructure import models as _finance  # noqa: F401
from restaurante.modules.identity.infrastructure import models as _identity  # noqa: F401
from restaurante.modules.inventory.infrastructure import models as _inventory  # noqa: F401
from restaurante.modules.kitchen.infrastructure import models as _kitchen  # noqa: F401
from restaurante.modules.menu.infrastructure import models as _menu  # noqa: F401
from restaurante.modules.messaging.infrastructure import models as _messaging  # noqa: F401
from restaurante.modules.orders.infrastructure import models as _orders  # noqa: F401
from restaurante.modules.purchasing.infrastructure import models as _purchasing  # noqa: F401
from restaurante.modules.recipes.infrastructure import models as _recipes  # noqa: F401
from restaurante.modules.staff.infrastructure import models as _staff  # noqa: F401
from restaurante.shared.audit import models as _audit  # noqa: F401
from restaurante.shared.tenancy import models as _tenancy  # noqa: F401
