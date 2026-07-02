"""Tests de la configuración: validación fail-closed del secreto JWT."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from restaurante.shared.config import Settings

_STRONG_SECRET = "a" * 40


def _settings(**overrides: object) -> Settings:
    # `_env_file=None` evita leer un `.env` real durante la prueba.
    base: dict[str, object] = {
        "jwt_secret": _STRONG_SECRET,
        "debug": False,
        "_env_file": None,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_secreto_fuerte_en_produccion_es_valido() -> None:
    settings = _settings()
    assert settings.jwt_secret == _STRONG_SECRET


def test_secreto_por_defecto_falla_en_produccion() -> None:
    with pytest.raises(ValidationError):
        _settings(jwt_secret="change-me-in-production")


def test_secreto_corto_falla_en_produccion() -> None:
    with pytest.raises(ValidationError):
        _settings(jwt_secret="corto")


def test_secreto_debil_permitido_en_debug() -> None:
    settings = _settings(jwt_secret="corto", debug=True)
    assert settings.debug is True
