"""Adaptador de hashing de contraseñas (Argon2). Implementa el puerto PasswordHasher.

Satisface estructuralmente `identity.domain.ports.PasswordHasher` sin importarlo
(tipado por Protocol), manteniendo la capa shared desacoplada de los módulos.
"""

from __future__ import annotations

from pwdlib import PasswordHash


class Argon2PasswordHasher:
    def __init__(self) -> None:
        # `recommended()` usa Argon2 cuando está instalado el extra correspondiente.
        self._hasher = PasswordHash.recommended()

    def hash(self, plain: str) -> str:
        return self._hasher.hash(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        return self._hasher.verify(plain, hashed)
