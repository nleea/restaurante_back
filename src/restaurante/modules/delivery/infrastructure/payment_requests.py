"""Small security primitives for quote-scoped payment links."""

from __future__ import annotations

import hashlib
import secrets


def issue_payment_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode("utf-8")).hexdigest()


def hash_payment_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
