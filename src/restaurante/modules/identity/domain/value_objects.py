"""Value objects del dominio de identidad."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Email:
    """Email normalizado (minúsculas, sin espacios).

    La validación de formato fuerte se delega a Pydantic en la capa de API
    (`EmailStr`); aquí sólo garantizamos una forma canónica para comparaciones.
    """

    value: str

    @classmethod
    def normalize(cls, raw: str) -> str:
        return raw.strip().lower()

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", self.normalize(self.value))
