"""Errores de dominio transversales.

El dominio lanza estas excepciones sin conocer HTTP; la capa de API las traduce
a respuestas (ver `shared.api.errors`).
"""

from __future__ import annotations


class DomainError(Exception):
    """Error base de la capa de dominio."""

    code: str = "domain_error"

    def payload(self) -> dict[str, object]:
        """Datos extra que el front necesita para reaccionar, no sólo para leer.

        Se fusionan en el cuerpo de la respuesta junto a `code` y `detail` (ver
        `shared.api.errors`). Por defecto vacío: sólo lo sobreescriben los errores
        que llevan un dato accionable (p. ej. quién tomó ya la conversación).
        """
        return {}


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


class BranchNotFoundError(DomainError):
    """La sucursal direccionada no existe (o está inactiva) en el tenant.

    Código propio, distinto de `not_found`, porque el storefront público direcciona la
    sucursal por `branches.code` en la URL: el front necesita distinguir "esa sede no
    existe" (ofrecer el selector) de cualquier otro 404. Nunca se cae a la sucursal
    principal — un pedido en la cocina equivocada no es recuperable.
    """

    code = "branch_not_found"


class ConflictError(DomainError):
    """La operación choca con el estado actual (dependientes, duplicado, etc.)."""

    code = "conflict"


class CashClosedError(DomainError):
    """No hay una caja abierta en la sucursal: no se aceptan pedidos.

    La caja abierta es la frontera del turno operativo; sin ella no se crea ningún
    pedido (salón, storefront, domicilio). Código propio para que el front pinte el
    estado "caja cerrada", distinto de un 422 de validación.
    """

    code = "cash_closed"


class ValidationError(DomainError):
    """Datos válidos en forma pero que violan una regla de negocio.

    P.ej. un rango horario invertido o una hora de salida anterior a la entrada.
    La capa de API la traduce a 422.
    """

    code = "validation_error"


class TenantNotResolvedError(DomainError):
    """No se pudo resolver el tenant del request (subdominio ausente/desconocido)."""

    code = "tenant_not_resolved"
