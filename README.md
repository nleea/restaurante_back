# Restaurante App

SaaS **multitenant** de gestión de restaurantes. Backend en **FastAPI** + **SQLAlchemy 2.0
async**, arquitectura **hexagonal** (puertos y adaptadores), tenancy **row-level** por
`tenant_id` con resolución del tenant por **subdominio**.

> Alcance funcional y decisiones de producto: ver `docs/Primer Alcance.md` y `CLAUDE.md`.

## Stack

- FastAPI · SQLAlchemy 2.0 (asyncpg) · PostgreSQL · Alembic
- JWT access + refresh (PyJWT) · Argon2 (pwdlib)
- Poetry · pytest · ruff · mypy

## Arquitectura

```
src/restaurante/
├── shared/            # núcleo transversal: config, db, tenancy, security, api
└── modules/
    └── identity/      # módulo de Identidad y Accesos (login)
        ├── domain/         # entidades, value objects, puertos (interfaces)
        ├── application/     # casos de uso + DTOs (orquesta el dominio)
        └── infrastructure/ # adaptadores: ORM, repos, API (router/schemas/deps)
```

Regla de dependencia: `API → application → domain`; `infrastructure` implementa los
puertos del `domain`. El dominio no importa frameworks.

## Puesta en marcha

```bash
cp .env.example .env                 # ajustar JWT_SECRET, etc.
docker compose up -d db              # Postgres local
poetry install
poetry run alembic upgrade head      # crea tablas tenants/branches/users/audit_logs
poetry run python -m scripts.seed    # tenant demo + admin@demo.com / admin1234
poetry run uvicorn restaurante.main:app --reload
```

El tenant se resuelve por subdominio: `Host: <slug>.<BASE_DOMAIN>` (ej. `demo.api.local`).
Para probar localmente basta enviar el header `Host`:

```bash
curl -s http://localhost:8000/auth/login \
  -H "Host: demo.api.local" -H "Content-Type: application/json" \
  -d '{"email":"admin@demo.com","password":"admin1234"}'
```

## Comandos de desarrollo

```bash
poetry run pytest                    # tests (unit + integración con sqlite)
poetry run pytest tests/modules/identity/test_login_use_case.py::test_login_ok_emite_par_de_tokens
poetry run ruff check .              # lint
poetry run mypy src                  # tipos
poetry run alembic revision --autogenerate -m "mensaje"   # nueva migración
```
