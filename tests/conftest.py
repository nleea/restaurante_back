"""Configuración de pruebas: SQLite async en archivo + seed de tenant/usuario.

Las variables de entorno se fijan ANTES de importar la app, para que
`get_settings()` (cacheado) apunte a la base de datos de pruebas.
"""

from __future__ import annotations

import os
from pathlib import Path

_DB_PATH = Path(__file__).parent / "test.db"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_DB_PATH}"
# Secreto >= 32 bytes para satisfacer la validación de `Settings` y RFC 7518.
os.environ["JWT_SECRET"] = "test-secret-test-secret-test-secret-0123456789"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "15"
os.environ["REFRESH_TOKEN_EXPIRE_DAYS"] = "7"
os.environ["BASE_DOMAIN"] = "api.local"
os.environ["DEBUG"] = "false"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import event  # noqa: E402

import restaurante.shared.models_registry  # noqa: E402, F401  (registers all tables)
from restaurante.main import app  # noqa: E402
from restaurante.modules.identity.infrastructure.models import UserModel  # noqa: E402
from restaurante.shared.cache import get_cache  # noqa: E402
from restaurante.shared.database import Base, SessionFactory, engine  # noqa: E402
from restaurante.shared.security.password import Argon2PasswordHasher  # noqa: E402
from restaurante.shared.tenancy.models import TenantModel  # noqa: E402


# SQLite ignora las claves foráneas salvo que se active por conexión. Lo
# habilitamos para que los tests validen las constraints reales (RESTRICT, etc.),
# igual que en PostgreSQL en producción.
@event.listens_for(engine.sync_engine, "connect")
def _enable_sqlite_fk(dbapi_connection: object, _: object) -> None:
    cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


TENANT_SLUG = "demo"
TEST_EMAIL = "admin@demo.com"
TEST_PASSWORD = "admin1234"


async def _drop_all_no_fk(conn: object) -> None:
    """Drop all tables with FK enforcement off.

    SQLite performs an implicit DELETE when dropping a table under
    ``PRAGMA foreign_keys=ON``; with self-referential tables (e.g.
    ``units_of_measure``) that implicit delete can violate the constraint.
    Teardown DDL must not enforce FKs, so we disable them just for the drop.
    """
    await conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
    await conn.run_sync(Base.metadata.drop_all)
    await conn.exec_driver_sql("PRAGMA foreign_keys=ON")


@pytest_asyncio.fixture
async def setup_db() -> None:
    async with engine.begin() as conn:
        await _drop_all_no_fk(conn)
        await conn.run_sync(Base.metadata.create_all)

    # Isolate the process-wide cache singleton between tests.
    await get_cache().clear()

    hasher = Argon2PasswordHasher()
    async with SessionFactory() as session:
        tenant = TenantModel(slug=TENANT_SLUG, name="Demo", is_active=True)
        session.add(tenant)
        await session.flush()
        session.add(
            UserModel(
                tenant_id=tenant.id,
                email=TEST_EMAIL,
                hashed_password=hasher.hash(TEST_PASSWORD),
                name="Demo Administrator",
                is_active=True,
            )
        )
        await session.commit()

    yield

    await get_cache().clear()
    async with engine.begin() as conn:
        await _drop_all_no_fk(conn)


@pytest_asyncio.fixture
async def client(setup_db: None) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://demo.api.local"
    ) as http_client:
        yield http_client
