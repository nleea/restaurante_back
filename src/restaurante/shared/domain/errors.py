"""Errores de dominio transversales.

El dominio lanza estas excepciones sin conocer HTTP; la capa de API las traduce
a respuestas (ver `shared.api.errors`).
"""

from __future__ import annotations


class DomainError(Exception):
    """Error base de la capa de dominio."""

    code: str = "domain_error"


class AuthenticationError(DomainError):
    """Credenciales inválidas o usuario no autenticable."""

    code = "authentication_error"


class InvalidTokenError(DomainError):
    """Token JWT inválido, expirado o de tipo incorrecto."""

    code = "invalid_token"


class AuthorizationError(DomainError):
    """El usuario está autenticado pero no tiene el permiso requerido."""

    code = "authorization_error"


class NotFoundError(DomainError):
    """No existe el recurso referenciado (rol, permiso, etc.)."""

    code = "not_found"


class ConflictError(DomainError):
    """La operación choca con el estado actual (dependientes, duplicado, etc.)."""

    code = "conflict"


class ValidationError(DomainError):
    """Datos válidos en forma pero que violan una regla de negocio.

    P.ej. un rango horario invertido o una hora de salida anterior a la entrada.
    La capa de API la traduce a 422.
    """

    code = "validation_error"


class TenantNotResolvedError(DomainError):
    """No se pudo resolver el tenant del request (subdominio ausente/desconocido)."""

    code = "tenant_not_resolved"
