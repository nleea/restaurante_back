"""The format rule for ``branches.code``.

``branches.code`` was always the tenant-readable identifier of a branch (see
`BranchModel`, unique per tenant). The public storefront now *addresses* a branch with
it — `<tenant-slug>.<domain>/store/<branch-code>` — which turns it into part of a URL a
customer receives over WhatsApp and pastes back. A code like ``Sede #1 (Centro)`` was
legal before and produces a broken link now.

Hence one rule, defined once here rather than restated at each writer:

    lowercase letters and digits, single hyphens between them, at most 32 characters

Kept in `shared` because branches live in `shared/tenancy` and `shared` must never
import from `modules`.
"""

from __future__ import annotations

import re

from restaurante.shared.domain.errors import ValidationError

# Anchored: the WHOLE code must match, and a hyphen may only sit between two segments
# (so `-centro`, `centro-` and `centro--norte` are all rejected).
BRANCH_CODE_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
BRANCH_CODE_MAX_LENGTH = 32


def is_valid_branch_code(code: str) -> bool:
    """Whether ``code`` is safe to place in a public URL path segment."""
    return (
        len(code) <= BRANCH_CODE_MAX_LENGTH
        and BRANCH_CODE_PATTERN.match(code) is not None
    )


def validate_branch_code(code: str) -> str:
    """Return ``code`` unchanged, or raise `ValidationError` explaining the rule.

    Raises rather than normalising: silently lowercasing ``Centro`` into ``centro``
    would mean the code stored differs from the code typed, and the link a tenant hands
    out would not be the one they think they configured.
    """
    if not is_valid_branch_code(code):
        raise ValidationError(
            f"Código de sucursal inválido: {code!r}. Debe llevar solo minúsculas, "
            f"dígitos y guiones simples entre ellos (máx. {BRANCH_CODE_MAX_LENGTH}), "
            "porque es parte de la URL pública de la carta."
        )
    return code
