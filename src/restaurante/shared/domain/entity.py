"""Base de entidades de dominio (puras, sin dependencias de frameworks)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass
class Entity:
    """Entidad de dominio identificada por un UUID."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)
