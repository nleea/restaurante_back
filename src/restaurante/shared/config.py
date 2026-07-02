"""Configuración de la aplicación, cargada desde variables de entorno / .env."""

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Secreto JWT por defecto: NUNCA debe usarse fuera de `debug`/desarrollo.
_INSECURE_DEFAULT_SECRET = "3d9bada11447945502abc576afa73f8b4523c1ee61d80c9e82f60775239b4eae"
# Longitud mínima para HS256 (RFC 7518 §3.2: >= 32 bytes).
_MIN_JWT_SECRET_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Aplicación
    app_name: str = "Restaurante API"
    debug: bool = False
    # Dominio base para resolver el tenant: <slug>.<base_domain>
    base_domain: str = "api.local"

    # CORS: el navegador exige que la API autorice el origen del front. El front corre en
    # <slug>.<base_domain>:<port> (un subdominio por tenant), por lo que un patrón (regex)
    # cubre todos los subdominios de tenant. El valor por defecto habilita cualquier
    # *.localhost en cualquier puerto (desarrollo); en producción defina
    # CORS_ALLOW_ORIGIN_REGEX con el/los dominio(s) reales del front.
    cors_allow_origin_regex: str = r"https?://([a-z0-9-]+\.)?localhost(:\d+)?"

    # Base de datos (SQLAlchemy async)
    database_url: str = (
        "postgresql+asyncpg://restaurante:restaurante@localhost:5432/restaurante"
    )

    # JWT
    jwt_secret: str = _INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # Cache: backend "memory" (per process, dev/tests) or "redis" (distributed).
    cache_backend: str = "memory"
    redis_url: str = "redis://localhost:6379/0"
    cache_ttl_seconds: int = 300

    @model_validator(mode="after")
    def _validate_jwt_secret(self) -> "Settings":
        """Fail-closed: en producción el secreto JWT debe ser fuerte y propio.

        En un SaaS multi-tenant, un secreto débil o por defecto permite forjar
        tokens y cruzar la frontera entre tenants. Sólo se permite relajar esta
        regla con `debug=True` (desarrollo/pruebas).
        """
        if self.debug:
            return self
        if self.jwt_secret == _INSECURE_DEFAULT_SECRET:
            raise ValueError(
                "JWT_SECRET no puede usar el valor por defecto en producción. "
                "Defina un secreto propio (>= 32 bytes)."
            )
        if len(self.jwt_secret.encode("utf-8")) < _MIN_JWT_SECRET_LENGTH:
            raise ValueError(
                "JWT_SECRET es demasiado corto: se requieren al menos "
                f"{_MIN_JWT_SECRET_LENGTH} bytes para HS256 (RFC 7518)."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Devuelve la configuración como singleton cacheado."""
    return Settings()
